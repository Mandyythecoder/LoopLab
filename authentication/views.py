import os
import uuid
import logging
import requests
import re

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from django.shortcuts import render
from yt_dlp import YoutubeDL
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from .forms import CustomUserCreationForm
from django.urls import reverse
from django.contrib.auth import logout
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """Removes invalid characters for filenames and trims extra spaces."""
    return re.sub(r'[\/:*?"<>|]', '', filename).strip()

FREESOUND_API_KEY = "EWnzJbweQbG1I7r0Ur4yHgnq2Kim7e7UCfuDYae3"
FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
FREESOUND_SOUND_DETAILS_URL = "https://freesound.org/apiv2/sounds/{}/"

def index(request):
    return render(request, 'index.html', {'is_authenticated': request.user.is_authenticated})
def fetch_sound_details(sound_id):
    cache_key = f"sound_{sound_id}"
    sound_data = cache.get(cache_key)

    if not sound_data:
        response = requests.get(
            FREESOUND_SOUND_DETAILS_URL.format(sound_id),
            params={"token": FREESOUND_API_KEY}
        )
        if response.status_code == 200:
            sound_data = response.json()
            cache.set(cache_key, sound_data, timeout=3600)
        else:
            logger.error(f"Failed to fetch details for sound ID {sound_id}: {response.status_code}")
            return None
    
    return sound_data


def search_sounds(request):
    query = request.GET.get('query', '').strip()
    sounds = []

    if query:
        response = requests.get(
            FREESOUND_SEARCH_URL,
            params={"query": query, "token": FREESOUND_API_KEY, "page_size": 50}
        )

        if response.status_code == 200:
            data = response.json()
            sound_results = data.get("results", [])

            for sound in sound_results:
                sound_id = sound["id"]
                sound_details = fetch_sound_details(sound_id)

                if sound_details:
                    preview_url = sound_details.get("previews", {}).get("preview-hq-mp3")
                    sounds.append({
                        "name": sound_details["name"],
                        "preview_url": preview_url
                    })
        else:
            logger.error(f"Error fetching search results: {response.status_code}")

    return render(request, 'search_results.html', {
        'sounds': sounds,
        'query': query,
        'no_results': not sounds
    })


def library_view(request):
    query = request.GET.get('query') or request.GET.get('q') or "music"
    query = query.strip()
    
    page_number = request.GET.get('page', 1)
    per_page = 15

    cache_key = f"library_sounds_{query}"
    sounds = cache.get(cache_key)

    if sounds is None:
        response = requests.get(
            FREESOUND_SEARCH_URL,
            params={"query": query, "token": FREESOUND_API_KEY, "page_size": 50}
        )
        sounds = []
        if response.status_code == 200:
            data = response.json()
            sound_results = data.get("results", [])

            for sound in sound_results:
                sound_id = sound["id"]
                sound_details = fetch_sound_details(sound_id)

                if sound_details:
                    preview_url = sound_details.get("previews", {}).get("preview-hq-mp3")
                    if preview_url:
                        sounds.append({
                            "name": sound_details["name"],
                            "preview_url": preview_url
                        })

        cache.set(cache_key, sounds, timeout=600)

    paginator = Paginator(sounds, per_page)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    return render(request, 'library.html', {
        'sounds': page_obj,
        'query': query,
        'no_results': not bool(sounds)
    })

def login_view(request):
    login_failed = False
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('index')
        else:
            login_failed = True
            messages.error(request, "Invalid credentials, please try again.")
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {
        'form': form,
        'login_failed': login_failed
    })

    
    
def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('/login/?signup=success')
        else:
            print("Form errors:", form.errors)
    else:
        form = CustomUserCreationForm()
    return render(request, 'login.html', {'form': form})

def custom_logout(request):
    logout(request)
    request.session.flush()
    return redirect('index') 

def editor_view(request):
    sound_url = request.GET.get('sound_url', '')
    return render(request, 'editor.html', {'sound_url': sound_url})


def rename_converted_file(old_path):
    """Fix double extension issue"""
    if old_path.endswith(".mp3.mp3"):
        new_path = old_path.replace(".mp3.mp3", ".mp3")
        os.rename(old_path, new_path)
        return new_path
    return old_path


def converter(request):
    if request.method == "POST":
        youtube_url = request.POST.get("youtube_url")

        if "youtube.com" not in youtube_url and "youtu.be" not in youtube_url:
            return render(request, "converter.html", {"error": "❌ Invalid YouTube URL."})

        try:
            with YoutubeDL({'quiet': True}) as ydl:
                info_dict = ydl.extract_info(youtube_url, download=False)
                video_title = sanitize_filename(info_dict.get("title", "converted_audio"))
                print(f"🎵 Video Title: {video_title}")

            output_filename = f"{video_title}.mp3"
            output_path = os.path.join(settings.MEDIA_ROOT, output_filename)

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(settings.MEDIA_ROOT, f"{video_title}.%(ext)s"),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'verbose': True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])

            final_path = rename_converted_file(output_path)

            print(f"✅ Saved file: {final_path}")
            if not os.path.exists(final_path):
                print("❌ File NOT FOUND after supposed save.")
                return render(request, "converter.html", {"error": "⚠️ File not found after conversion."})

            mp3_url = request.build_absolute_uri(settings.MEDIA_URL + os.path.basename(final_path))
            return render(request, "converter.html", {"mp3_url": mp3_url})

        except Exception as e:
            print(f"⚠️ ERROR: {e}")
            return render(request, "converter.html", {"error": f"⚠️ Conversion failed: {str(e)}"})

    return render(request, "converter.html")



