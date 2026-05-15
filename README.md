# Система управления мобильной библиотекой

## Требования

- Python 3.11 или выше → https://python.org/downloads
  (при установке поставь галочку "Add Python to PATH")
- Git → https://git-scm.com/downloads

## Установка (выполняй по порядку)

### 1. Скачать проект
git clone https://github.com/ТУТ-ТВОЙ-РЕПОЗИТОРИЙ.git
cd library-system

### 2. Создать виртуальное окружение
python -m venv venv

### 3. Активировать виртуальное окружение

# Windows (командная строка cmd):
venv\Scripts\activate.bat

# Windows (PowerShell):
venv\Scripts\Activate.ps1

# Mac / Linux:
source venv/bin/activate

# После активации в начале строки появится (venv)

### 4. Установить зависимости
pip install -r requirements.txt

### 5. Создать файл настроек
copy .env.example .env
# Открой файл .env и заполни LIBRARY_NAME и LIBRARY_PHONE

### 6. Создать базу данных
python manage.py migrate

### 7. Создать учётную запись администратора
python manage.py createsuperuser

### 8. Загрузить тестовые данные
python manage.py seed_data

## Запуск

python manage.py runserver

Открой в браузере:
- Кабинет библиотекаря: http://127.0.0.1:8000/admin-panel/
- Публичный каталог:    http://127.0.0.1:8000/

## Остановка

Нажми Ctrl+C в терминале где запущен сервер.

## Повторный запуск

cd library-system
venv\Scripts\activate.bat
python manage.py runserver
