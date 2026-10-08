from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.
class Book(models.Model):
    title = models.CharField(max_length=50)
    autor = models.CharField(max_length=50)
    goal = models.DateField(null=True, blank=True)
    pages_read = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    pages_total = models.IntegerField(validators=[MinValueValidator(1)])
    created = models.DateField(auto_now_add=True)
    date_completed = models.DateField(null=True, blank=True, default=None)
    user =  models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Nuevos campos para Milestone 1
    cover = models.ImageField(upload_to='covers/', null=True, blank=True)
    pdf_file = models.FileField(upload_to='pdfs/', null=True, blank=True)
    google_books_id = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.title
    
    def progress(self):
        if self.pages_total == 0:
            return 0
        return round((self.pages_read / self.pages_total) * 100)
    
    def pages_for_day(self):
        if self.pages_total == 0:
            return 0
        tabla = []
        for dias in range(1, 11):
            paginas_por_dia = round((self.pages_total-self.pages_read) / dias)
            tabla.append((dias, paginas_por_dia))
        return tabla

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pages_read > self.pages_total:
            raise ValidationError("Las páginas leídas no pueden ser mayores que el total de páginas.")

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    date_most_pages_read = models.DateField(null=True, blank=True)
    most_pages_read = models.PositiveIntegerField(default=0)
    pages_this_month = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Perfil de {self.user.username}"
    
    def average_pages_for_day(self):
        if self.pages_this_month == 0:
            return 0
        dias = timezone.now().day
        paginas_por_dia = round(self.pages_this_month / dias)
        return paginas_por_dia

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        instance.profile.save()
