import datetime
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Book, Profile
from django.core.files.uploadedfile import SimpleUploadedFile

class MVT_BookModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')

    def test_mvt_1_book_creation_without_metadata(self):
        book = Book.objects.create(title='Test Book', autor='Author', pages_total=100, user=self.user)
        self.assertEqual(book.title, 'Test Book')
        self.assertIsNone(book.cover.name if book.cover else None)

    def test_mvt_2_book_progress_calculation_zero(self):
        book = Book(title='Test', autor='A', pages_read=0, pages_total=100, user=self.user)
        self.assertEqual(book.progress(), 0)

    def test_mvt_3_book_progress_calculation_half(self):
        book = Book(title='Test', autor='A', pages_read=50, pages_total=100, user=self.user)
        self.assertEqual(book.progress(), 50)

    def test_mvt_4_book_progress_calculation_full(self):
        book = Book(title='Test', autor='A', pages_read=100, pages_total=100, user=self.user)
        self.assertEqual(book.progress(), 99, "Fallo intencional: Simulando bug de redondeo en 100%")

    def test_mvt_5_book_pages_for_day_calculation(self):
        book = Book(title='Test', autor='A', pages_read=0, pages_total=100, user=self.user)
        tabla = book.pages_for_day()
        self.assertEqual(len(tabla), 10)
        self.assertEqual(tabla[0], (1, 100))
        self.assertEqual(tabla[9], (10, 10))

    def test_mvt_6_profile_created_on_user_creation(self):
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_mvt_7_profile_average_pages_for_day(self):
        profile = self.user.profile
        profile.pages_this_month = 100
        profile.save()
        # El promedio dependerá del día actual
        dias = timezone.now().day
        self.assertEqual(profile.average_pages_for_day(), round(100 / dias))

    def test_mvt_8_book_str_representation(self):
        book = Book(title='Representation Test', autor='A', pages_total=10, user=self.user)
        self.assertEqual(str(book), 'Representation Test')

    def test_mvt_9_profile_str_representation(self):
        profile = self.user.profile
        self.assertEqual(str(profile), 'Perfil de testuser')

    def test_mvt_10_clean_validation(self):
        book = Book(title='Test', autor='A', pages_read=150, pages_total=100, user=self.user)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            book.clean()


class IVT_ViewsIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.login(username='testuser', password='password')
        self.book = Book.objects.create(title='IVT Book', autor='Author', pages_total=100, user=self.user)

    def test_ivt_1_create_book_view_get(self):
        response = self.client.get('/books/create/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'create_book.html')

    @patch('requests.get')
    def test_ivt_2_create_book_view_post_valid(self, mock_get):
        mock_get.return_value.status_code = 404 # Simular que no encuentra en API
        response = self.client.post('/books/create/', {
            'title': 'New Integration Book',
            'autor': 'Test Author',
            'pages_total': 200,
            'pages_read': 0
        })
        self.assertEqual(response.status_code, 302) # Redirect to books
        self.assertTrue(Book.objects.filter(title='New Integration Book').exists())

    def test_ivt_3_create_book_view_invalid_pages(self):
        response = self.client.post('/books/create/', {
            'title': 'Error Book',
            'autor': 'Test Author',
            'pages_total': 100,
            'pages_read': 150
        })
        self.assertEqual(response.status_code, 302, "Fallo intencional: Se esperaba que pasara la validación errónea (Bug de Backend)")

    def test_ivt_4_book_detail_view_get(self):
        response = self.client.get(f'/books/{self.book.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'IVT Book')

    def test_ivt_5_book_detail_view_post_valid_updates_db(self):
        response = self.client.post(f'/books/{self.book.id}/', {
            'title': 'IVT Book Updated',
            'autor': 'Author',
            'pages_total': 100,
            'pages_read': 10
        })
        self.assertEqual(response.status_code, 302)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, 'IVT Book Updated')

    def test_ivt_6_book_detail_view_post_invalid(self):
        response = self.client.post(f'/books/{self.book.id}/', {
            'title': 'IVT Book Updated',
            'autor': 'Author',
            'pages_total': 100,
            'pages_read': 150 # Invalid
        })
        self.assertContains(response, 'No puedes leer más páginas de las que tiene el libro')

    def test_ivt_7_complete_book_view(self):
        response = self.client.post(f'/books/{self.book.id}/complete')
        self.assertEqual(response.status_code, 302)
        self.book.refresh_from_db()
        self.assertEqual(self.book.pages_read, self.book.pages_total)

    def test_ivt_8_delete_book_view(self):
        response = self.client.post(f'/books/{self.book.id}/delete')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Book.objects.filter(id=self.book.id).exists())

    def test_ivt_9_dashboard_view(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')

    def test_ivt_10_signup_view_creates_user(self):
        self.client.logout()
        response = self.client.post('/signup/', {
            'username': 'newuser',
            'password1': 'securepass',
            'password2': 'securepass'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())


class SVT_SystemValidationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_svt_1_unauthenticated_user_redirected_to_login(self):
        response = self.client.get('/books/')
        self.assertRedirects(response, '/signin/?next=/books/')

    def test_svt_2_user_can_signup_and_redirect_to_books(self):
        response = self.client.post('/signup/', {
            'username': 'svtuser',
            'password1': 'testpass',
            'password2': 'testpass'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books.html')

    def test_svt_3_user_login_flow(self):
        User.objects.create_user(username='svtlogin', password='password')
        response = self.client.post('/signin/', {
            'username': 'svtlogin',
            'password': 'password'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books.html')

    def test_svt_4_create_book_flow_displays_on_library(self):
        User.objects.create_user(username='svt', password='password')
        self.client.login(username='svt', password='password')
        self.client.post('/books/create/', {
            'title': 'SVT Library Book',
            'autor': 'Author',
            'pages_total': 300,
            'pages_read': 0
        })
        response = self.client.get('/books/')
        self.assertContains(response, 'SVT Library Book')

    @patch('requests.get')
    def test_svt_5_create_book_with_pdf_flow(self, mock_get):
        mock_get.return_value.status_code = 404
        User.objects.create_user(username='svt5', password='password')
        self.client.login(username='svt5', password='password')
        
        pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n/Title (Dummy PDF)\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF'
        pdf_file = SimpleUploadedFile("dummy.pdf", pdf_content, content_type="application/pdf")
        
        response = self.client.post('/books/create/', {
            'title': 'SVT PDF Book',
            'autor': 'Author',
            'pages_total': 100,
            'pages_read': 0,
            'pdf_file': pdf_file
        })
        book = Book.objects.get(title='SVT PDF Book')
        print("PDF FILE IS:", book.pdf_file, bool(book.pdf_file))
        self.assertTrue(bool(book.pdf_file), msg=f"PDF file is empty. Expected dummy.pdf")

    def test_svt_6_update_book_progress_updates_dashboard(self):
        user = User.objects.create_user(username='svt6', password='password')
        self.client.login(username='svt6', password='password')
        book = Book.objects.create(title='Dash Book', autor='A', pages_total=100, user=user)
        self.client.post(f'/books/{book.id}/', {
            'title': 'Dash Book',
            'autor': 'A',
            'pages_total': 100,
            'pages_read': 50
        })
        response = self.client.get('/dashboard/')
        self.assertContains(response, 'Dash Book') # El dashboard incluye el libro

    def test_svt_7_complete_book_flow_updates_library(self):
        user = User.objects.create_user(username='svt', password='password')
        self.client.login(username='svt', password='password')
        book = Book.objects.create(title='To Complete', autor='A', pages_total=100, pages_read=0, user=user)
        self.client.post(f'/books/{book.id}/complete')
        response = self.client.get('/books/')
        # 100 de 100 must be somewhere or the progress bar 100%
        self.assertContains(response, 'width: 100%')

    def test_svt_8_delete_book_flow_removes_from_library(self):
        user = User.objects.create_user(username='svt', password='password')
        self.client.login(username='svt', password='password')
        book = Book.objects.create(title='To Delete', autor='A', pages_total=100, user=user)
        self.client.post(f'/books/{book.id}/delete')
        response = self.client.get('/books/')
        self.assertContains(response, 'To Delete') # Fallo intencional: Simulando que el UI no actualiza el libro borrado

    def test_svt_9_pdf_viewer_renders_if_pdf_uploaded(self):
        user = User.objects.create_user(username='svt', password='password')
        self.client.login(username='svt', password='password')
        pdf_file = SimpleUploadedFile("test.pdf", b"test content", content_type="application/pdf")
        book = Book.objects.create(title='PDF View Book', autor='A', pages_total=100, user=user, pdf_file=pdf_file)
        
        response = self.client.get(f'/books/{book.id}/')
        self.assertContains(response, 'Visor PDF')
        self.assertContains(response, '<iframe')

    @patch('requests.get')
    def test_svt_10_google_books_metadata_saved_on_create(self, mock_get):
        # Mocker la respuesta de Google Books API
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "items": [{
                        "id": "12345",
                        "volumeInfo": {
                            "description": "Una gran historia mockeada"
                        }
                    }]
                }
        mock_get.return_value = MockResponse()
        
        user = User.objects.create_user(username='svt', password='password')
        self.client.login(username='svt', password='password')
        self.client.post('/books/create/', {
            'title': 'Harry Potter',
            'autor': 'J.K',
            'pages_total': 300,
            'pages_read': 0
        })
        book = Book.objects.get(title='Harry Potter')
        self.assertEqual(book.google_books_id, '12345')
        self.assertEqual(book.description, 'Una gran historia mockeada')
