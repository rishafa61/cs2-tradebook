@echo off
cd /d D:\tradebook

:: Start Django server
call .venv\Scripts\activate
python manage.py runserver 127.0.0.1:8000