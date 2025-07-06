# apps/users/views/auth_views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from ..forms import LoginForm, SignupForm


def login_view(request):
    """Login sahifasi"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = LoginForm()

    if request.method == 'POST':
        form = LoginForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data['remember_me']

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)

                # Remember me functionality
                if not remember_me:
                    request.session.set_expiry(0)  # Browser yopilganda session tugaydi

                messages.success(request, f'Xush kelibsiz, {user.username}!')
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Username yoki parol xato!')
        else:
            messages.error(request, 'Iltimos, formani to\'g\'ri to\'ldiring!')

    return render(request, 'auth/login.html', {'form': form})


def signup_view(request):
    """Signup sahifasi"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = SignupForm()

    if request.method == 'POST':
        form = SignupForm(request.POST)

        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Akkaunt muvaffaqiyatli yaratildi! Endi tizimga kirishingiz mumkin.')
            return redirect('login')
        else:
            messages.error(request, 'Iltimos, xatolarni tuzating!')

    return render(request, 'auth/signup.html', {'form': form})


@login_required
def logout_view(request):
    """Logout"""
    username = request.user.username
    logout(request)
    messages.success(request, f'{username}, tizimdan muvaffaqiyatli chiqdingiz!')
    return redirect('login')
