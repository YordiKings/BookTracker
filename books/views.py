from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.db import IntegrityError
from django.utils import timezone
from .forms import BookForm
from .forms import SignUpForm
from .forms import SignInForm
from .models import Book, Profile
from datetime import datetime
import requests
from django.core.files.base import ContentFile
import json
import os
from django.conf import settings

# Create your views here.

def home(request):
    return render(request, 'home.html')

def signup(request):
    if request.method == 'GET':
        return render(request, 'signup.html', {'form': SignUpForm()})
    else:
        if request.POST['password1'] == request.POST['password2']:
            # Registrar el usuario
            try:
                user = User.objects.create_user(username=request.POST['username'], password=request.POST['password1'])
                user.save()
                login(request, user)
                return redirect('books')
            except IntegrityError:
                return render(request, 'signup.html', {'form': SignUpForm(), 'error': 'El usuario ya existe'})
        return render(request, 'signup.html', {'form': SignUpForm(), 'error': 'Las contraseñas no coinciden'})

@login_required
def books(request):
    books = Book.objects.filter(user=request.user)
    return render(request, 'books.html', {'books': books})

@login_required
def dashboard(request):
    books_created = Book.objects.filter(user=request.user).order_by('-created')
    books_completed = Book.objects.filter(user=request.user, date_completed__isnull=False).order_by('-date_completed')
    profile = request.user.profile
    return render(request, 'dashboard.html', {'books_created': books_created, 'books_completed': books_completed, 'profile': profile})



@login_required
def create_book(request):
    profile = request.user.profile
    if request.method == 'GET':
        return render(request, 'create_book.html', {'form': BookForm()})
    else:
        form = BookForm(request.POST, request.FILES)
        pages_read = int(request.POST.get('pages_read', 0))
        pages_total = int(request.POST.get('pages_total', 0))
        book_id = int(request.POST.get('book_id', 0))
        if pages_read > pages_total:
            return render(request, 'create_book.html',{'form': form, 'error': 'No puedes leer más páginas de las que tiene el libro'})
        if form.is_valid():
            try:
                if pages_read == pages_total:
                    pass # Evitamos error por llamar complete_book sin id aún
                new_book = form.save(commit=False)
                new_book.user = request.user
                
                # Fetch metadata from Google Books
                query = f"intitle:{new_book.title}"
                if new_book.autor:
                    query += f"+inauthor:{new_book.autor}"
                response = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1")
                if response.status_code == 200 and 'items' in response.json():
                    item = response.json()['items'][0]
                    new_book.google_books_id = item.get('id')
                    new_book.description = item.get('volumeInfo', {}).get('description', '')
                    
                    # Fetch cover if no cover was provided manually
                    if not new_book.cover:
                        cover_url = item.get('volumeInfo', {}).get('imageLinks', {}).get('thumbnail')
                        if cover_url:
                            # Algunas URLs vienen http, es mejor https
                            cover_url = cover_url.replace('http:', 'https:')
                            img_response = requests.get(cover_url)
                            if img_response.status_code == 200:
                                new_book.cover.save(f"{new_book.title}_cover.jpg", ContentFile(img_response.content), save=False)

                new_book.save()
                
                if pages_read == pages_total:
                    complete_book(request, new_book.id)
                
                today = timezone.now().date()
                # Actualizar récord diario/máximo
                if profile.date_most_pages_read == today:
                        profile.most_pages_read += pages_read
                else:
                    if pages_read > profile.most_pages_read:
                        profile.most_pages_read = pages_read
                        profile.date_most_pages_read = today
                if profile.most_pages_read < 0:
                    profile.most_pages_read = 0
                profile.pages_this_month += pages_read
                if profile.pages_this_month < 0:
                    profile.pages_this_month = 0
                profile.save()
                return redirect('books')
            except ValueError:
                return render(request, 'create_book.html', {'form': form, 'error': 'Por favor ponga datos válidos'})
        else:
            return render(request, 'create_book.html', {'form': form, 'error': 'Formulario inválido'})

@login_required
def book_detail(request, book_id):
    book = get_object_or_404(Book, pk=book_id, user=request.user)
    profile = request.user.profile
    last_pages_read = book.pages_read  # <- correcto: tomamos el valor guardado
    if request.method == 'GET':
        form = BookForm(instance=book)
        return render(request, 'book_detail.html', {'book': book, 'form': form})
    else:
        form = BookForm(request.POST, request.FILES, instance=book)
        pages_read = int(request.POST.get('pages_read', 0))
        pages_total = int(request.POST.get('pages_total', 0))
        if pages_read > pages_total:
            return render(request, 'book_detail.html', {'book': book, 'form': form, 'error': 'No puedes leer más páginas de las que tiene el libro'})
        if form.is_valid():
            try:
                form.save()  # guardamos el libro actualizado primero
                if pages_read == pages_total:
                    complete_book(request, book_id)
                elif pages_read < pages_total:
                    book.date_completed = None
                    book.save()
                # Calcular cuántas páginas nuevas se leyeron
                pages = pages_read - last_pages_read
                today = timezone.now().date()
                current_month = today.month
                # Actualizar récord diario/máximo
                if profile.date_most_pages_read == today:
                        profile.most_pages_read += pages
                else:
                    if pages > profile.most_pages_read:
                        profile.most_pages_read = pages
                        profile.date_most_pages_read = today
                if profile.most_pages_read < 0:
                    profile.most_pages_read = 0
                # Reiniciar contador mensual si cambió el mes
                if profile.date_most_pages_read.month != current_month:
                    profile.pages_this_month = 0
                profile.pages_this_month += pages
                if profile.pages_this_month < 0:
                    profile.pages_this_month = 0
                profile.save()
                return redirect('books')
            except ValueError:
                return render(request, 'book_detail.html', {'book': book, 'form': form, 'error': 'Error actualizando libro'})
        else:
            return render(request, 'book_detail.html', {'book': book, 'form': form, 'error': 'Formulario inválido'})

@login_required
def complete_book(request, book_id):
    book = get_object_or_404(Book, pk=book_id, user=request.user)
    if request.method == 'POST':
        book.pages_read = book.pages_total
        book.date_completed = timezone.now()
        book.save()
        return redirect('books')

@login_required    
def delete_book(request, book_id):
    book = get_object_or_404(Book, pk=book_id, user=request.user)
    if request.method == 'POST':
        book.delete()
        return redirect('books')

@login_required    
def signout(request):
    logout(request)
    return redirect('home')

def signin(request):
    if request.method == 'GET':
        return render(request, 'signin.html', {'form': SignInForm()})
    else:
        user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if user is None:
            return render(request, 'signin.html', {'form': SignInForm(), 'error': 'El usuario o la contraseña no son incorrectos'})
        else:
            login(request, user)
            return redirect('books')


@login_required
def agile_dashboard(request):
    # Ruta hacia el archivo JSON de métricas
    json_path = os.path.join(settings.BASE_DIR, "books", "data", "metrics.json")

    # Carga de datos dinámicos
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)
    else:
        # Fallback en caso de no encontrar el archivo
        metrics_data = {"sprints": [], "kpis_summary": {}}

    context = {
        "metrics": metrics_data,
        "metrics_json": json.dumps(metrics_data),
    }
    return render(request, "agile_dashboard.html", context)