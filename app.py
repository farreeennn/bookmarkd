import os
from flask import Flask, render_template, request, redirect, url_for, session, abort, g
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import database

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['WTF_CSRF_ENABLED'] = True

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

 
# DB helper
 

def get_db():
    if 'db' not in g:
        g.db = database.get_connection()
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# Auth helper


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

 
# Landing
 

@app.route('/')
def landing():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

 
# Auth routes
 

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        display_name = request.form.get('display_name', '').strip() or username

        if not username or not email or not password:
            error = 'All fields are required.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif len(username) > 50:
            error = 'Username must be under 50 characters.'
        else:
            db = get_db()
            existing = db.execute(
                'SELECT user_id FROM users WHERE email = ?', (email,)
            ).fetchone()
            if existing:
                error = 'An account with that email already exists.'
            else:
                hashed = generate_password_hash(password)
                db.execute(
                    'INSERT INTO users (username, email, hashed_password, display_name) VALUES (?, ?, ?, ?)',
                    (username, email, hashed, display_name)
                )
                db.commit()
                return redirect(url_for('login'))

    return render_template('auth/register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            error = 'Please enter your email and password.'
        else:
            db = get_db()
            user = db.execute(
                'SELECT * FROM users WHERE email = ?', (email,)
            ).fetchone()
            if not user or not check_password_hash(user['hashed_password'], password):
                error = 'Invalid email or password.'
            else:
                session.clear()
                session['user_id'] = user['user_id']
                session['display_name'] = user['display_name']
                return redirect(url_for('dashboard'))

    return render_template('auth/login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

 
# Dashboard
 

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    user_id = session['user_id']

    # currently reading books (up to 3 for the dashboard strip)
    currently_reading = db.execute(
        'SELECT * FROM books WHERE user_id = ? AND shelf_status = ? ORDER BY date_started DESC LIMIT 3',
        (user_id, 'currently_reading')
    ).fetchall()

    # reading goal
    goal = db.execute(
        'SELECT * FROM goals WHERE user_id = ? AND target_year = ?',
        (user_id, 2026)
    ).fetchone()

    # books finished this year
    finished_this_year = db.execute(
        '''SELECT COUNT(*) as count FROM books
           WHERE user_id = ? AND shelf_status = ? AND strftime('%Y', date_finished) = '2026' ''',
        (user_id, 'finished')
    ).fetchone()['count']

    goal_target = goal['target_book_count'] if goal else 0
    goal_progress = round((finished_this_year / goal_target * 100)) if goal_target > 0 else 0

    return render_template('dashboard.html',
        currently_reading=currently_reading,
        goal_target=goal_target,
        finished_this_year=finished_this_year,
        goal_progress=min(goal_progress, 100)
    )

 
# Books - shelves
 

@app.route('/shelves')
@login_required
def shelves():
    db = get_db()
    user_id = session['user_id']
    shelf = request.args.get('shelf', 'currently_reading')
    valid_shelves = ['currently_reading', 'want_to_read', 'finished', 'dnf']
    if shelf not in valid_shelves:
        shelf = 'currently_reading'

    books = db.execute(
        '''SELECT b.*, r.star_rating FROM books b
           LEFT JOIN reviews r ON b.book_id = r.book_id AND r.user_id = b.user_id
           WHERE b.user_id = ? AND b.shelf_status = ?
           ORDER BY b.rowid DESC''',
        (user_id, shelf)
    ).fetchall()

    total_books = db.execute(
        'SELECT COUNT(*) as count FROM books WHERE user_id = ?',
        (user_id,)
    ).fetchone()['count']

    return render_template('books/shelves.html',
        books=books,
        active_shelf=shelf,
        total_books=total_books
    )


@app.route('/books/add', methods=['GET', 'POST'])
@login_required
def add_book():
    error = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        genre = request.form.get('genre', '').strip()
        shelf_status = request.form.get('shelf_status', 'want_to_read')
        total_pages = request.form.get('total_pages', '').strip()
        current_page = request.form.get('current_page', '0').strip()
        date_started = request.form.get('date_started', '') or None
        date_finished = request.form.get('date_finished', '') or None
        cover_url = request.form.get('cover_url', '').strip()
        personal_notes = request.form.get('personal_notes', '').strip()
        dnf_note = request.form.get('dnf_note', '').strip()

        if not title or not author:
            error = 'Title and author are required.'
        else:
            valid_shelves = ['currently_reading', 'want_to_read', 'finished', 'dnf']
            if shelf_status not in valid_shelves:
                shelf_status = 'want_to_read'
            try:
                total_pages = int(total_pages) if total_pages else None
                current_page = int(current_page) if current_page else 0
            except ValueError:
                error = 'Page numbers must be whole numbers.'

            if not error:
                db = get_db()
                db.execute(
                    '''INSERT INTO books
                       (user_id, title, author, genre, shelf_status, total_pages,
                        current_page, date_started, date_finished, cover_url,
                        personal_notes, dnf_note)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (session['user_id'], title, author, genre, shelf_status,
                     total_pages, current_page, date_started, date_finished,
                     cover_url, personal_notes, dnf_note)
                )
                db.commit()
                return redirect(url_for('shelves', shelf=shelf_status))

    return render_template('books/add_book.html', error=error)


@app.route('/books/<int:book_id>')
@login_required
def book_detail(book_id):
    db = get_db()
    book = db.execute(
        'SELECT * FROM books WHERE book_id = ? AND user_id = ?',
        (book_id, session['user_id'])
    ).fetchone()
    if book is None:
        abort(404)

    review = db.execute(
        'SELECT * FROM reviews WHERE book_id = ? AND user_id = ?',
        (book_id, session['user_id'])
    ).fetchone()

    return render_template('books/detail.html', book=book, review=review)


@app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    db = get_db()
    book = db.execute(
        'SELECT * FROM books WHERE book_id = ? AND user_id = ?',
        (book_id, session['user_id'])
    ).fetchone()
    if book is None:
        abort(404)

    error = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        genre = request.form.get('genre', '').strip()
        shelf_status = request.form.get('shelf_status', book['shelf_status'])
        total_pages = request.form.get('total_pages', '').strip()
        current_page = request.form.get('current_page', '0').strip()
        date_started = request.form.get('date_started', '') or None
        date_finished = request.form.get('date_finished', '') or None
        cover_url = request.form.get('cover_url', '').strip()
        personal_notes = request.form.get('personal_notes', '').strip()
        dnf_note = request.form.get('dnf_note', '').strip()
        is_favourite = 1 if request.form.get('is_favourite') else 0

        if not title or not author:
            error = 'Title and author are required.'
        else:
            try:
                total_pages = int(total_pages) if total_pages else None
                current_page = int(current_page) if current_page else 0
            except ValueError:
                error = 'Page numbers must be whole numbers.'

            if not error:
                db.execute(
                    '''UPDATE books SET title=?, author=?, genre=?, shelf_status=?,
                       total_pages=?, current_page=?, date_started=?, date_finished=?,
                       cover_url=?, personal_notes=?, dnf_note=?, is_favourite=?
                       WHERE book_id=? AND user_id=?''',
                    (title, author, genre, shelf_status, total_pages, current_page,
                     date_started, date_finished, cover_url, personal_notes,
                     dnf_note, is_favourite, book_id, session['user_id'])
                )
                db.commit()
                return redirect(url_for('book_detail', book_id=book_id))

    return render_template('books/edit_book.html', book=book, error=error)

@app.route('/books/<int:book_id>/favourite', methods=['POST'])
@login_required
def toggle_favourite(book_id):
    db = get_db()
    book = db.execute(
        'SELECT * FROM books WHERE book_id = ? AND user_id = ?',
        (book_id, session['user_id'])
    ).fetchone()
    if book is None:
        abort(404)
    new_status = 0 if book['is_favourite'] else 1
    db.execute(
        'UPDATE books SET is_favourite = ? WHERE book_id = ? AND user_id = ?',
        (new_status, book_id, session['user_id'])
    )
    db.commit()
    return redirect(url_for('book_detail', book_id=book_id))

@app.route('/books/<int:book_id>/delete', methods=['POST'])
@login_required
def delete_book(book_id):
    db = get_db()
    book = db.execute(
        'SELECT * FROM books WHERE book_id = ? AND user_id = ?',
        (book_id, session['user_id'])
    ).fetchone()
    if book is None:
        abort(404)
    db.execute('DELETE FROM reviews WHERE book_id = ? AND user_id = ?', (book_id, session['user_id']))
    db.execute('DELETE FROM books WHERE book_id = ? AND user_id = ?', (book_id, session['user_id']))
    db.commit()
    return redirect(url_for('shelves'))

 
# Reviews
 

@app.route('/books/<int:book_id>/review', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    db = get_db()
    book = db.execute(
        'SELECT * FROM books WHERE book_id = ? AND user_id = ? AND shelf_status = ?',
        (book_id, session['user_id'], 'finished')
    ).fetchone()
    if book is None:
        abort(404)

    existing = db.execute(
        'SELECT * FROM reviews WHERE book_id = ? AND user_id = ?',
        (book_id, session['user_id'])
    ).fetchone()

    error = None
    if request.method == 'POST':
        star_rating = request.form.get('star_rating')
        review_text = request.form.get('review_text', '').strip()
        try:
            star_rating = int(star_rating)
            if star_rating < 1 or star_rating > 5:
                raise ValueError
        except (ValueError, TypeError):
            error = 'Please select a rating between 1 and 5.'

        if not error:
            if existing:
                db.execute(
                    'UPDATE reviews SET star_rating=?, review_text=? WHERE book_id=? AND user_id=?',
                    (star_rating, review_text, book_id, session['user_id'])
                )
            else:
                db.execute(
                    'INSERT INTO reviews (book_id, user_id, star_rating, review_text) VALUES (?, ?, ?, ?)',
                    (book_id, session['user_id'], star_rating, review_text)
                )
            db.commit()
            return redirect(url_for('book_detail', book_id=book_id))

    return render_template('books/review.html', book=book, existing=existing, error=error)

 
# Reading diary
 

from datetime import date

@app.route('/diary')
@login_required
def diary():
    db = get_db()
    user_id = session['user_id']
    entries = db.execute(
        '''SELECT d.*, b.title as book_title FROM diary_entries d
           LEFT JOIN books b ON d.book_id = b.book_id
           WHERE d.user_id = ?
           ORDER BY d.date_created DESC''',
        (user_id,)
    ).fetchall()
    books = db.execute(
        'SELECT book_id, title FROM books WHERE user_id = ? ORDER BY title',
        (user_id,)
    ).fetchall()
    return render_template('diary/diary.html', entries=entries, books=books,today=date.today().isoformat()
    )


@app.route('/diary/add', methods=['POST'])
@login_required
def add_diary_entry():
    entry_text = request.form.get('entry_text', '').strip()
    book_id = request.form.get('book_id') or None
    entry_date = request.form.get('entry_date', '').strip() or None
    if not entry_text:
        return redirect(url_for('diary'))
    if book_id:
        db = get_db()
        owns = db.execute(
            'SELECT book_id FROM books WHERE book_id = ? AND user_id = ?',
            (book_id, session['user_id'])
        ).fetchone()
        if not owns:
            book_id = None
    db = get_db()
    db.execute(
        'INSERT INTO diary_entries (user_id, book_id, entry_text, date_created) VALUES (?, ?, ?, ?)',
        (session['user_id'], book_id, entry_text, entry_date)
    )
    db.commit()
    return redirect(url_for('diary'))


@app.route('/diary/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete_diary_entry(entry_id):
    db = get_db()
    entry = db.execute(
        'SELECT * FROM diary_entries WHERE entry_id = ? AND user_id = ?',
        (entry_id, session['user_id'])
    ).fetchone()
    if entry is None:
        abort(404)
    db.execute('DELETE FROM diary_entries WHERE entry_id = ? AND user_id = ?',
               (entry_id, session['user_id']))
    db.commit()
    return redirect(url_for('diary'))

 
# Interactive bookshelf (favourites)
 

@app.route('/bookshelf')
@login_required
def bookshelf():
    db = get_db()
    favourites = db.execute(
        '''SELECT b.*, r.star_rating, r.review_text FROM books b
           LEFT JOIN reviews r ON b.book_id = r.book_id AND r.user_id = b.user_id
           WHERE b.user_id = ? AND b.is_favourite = 1
           ORDER BY b.title''',
        (session['user_id'],)
    ).fetchall()
    return render_template('bookshelf/bookshelf.html', favourites=favourites)

 
# Statistics and goals
 

@app.route('/stats')
@login_required
def stats():
    db = get_db()
    user_id = session['user_id']

    total_books = db.execute(
        'SELECT COUNT(*) as c FROM books WHERE user_id = ? AND shelf_status = ?',
        (user_id, 'finished')
    ).fetchone()['c']

    total_pages = db.execute(
        'SELECT COALESCE(SUM(total_pages), 0) as p FROM books WHERE user_id = ? AND shelf_status = ?',
        (user_id, 'finished')
    ).fetchone()['p']

    avg_rating = db.execute(
        'SELECT ROUND(AVG(star_rating), 1) as a FROM reviews WHERE user_id = ?',
        (user_id,)
    ).fetchone()['a']

    fav_genre = db.execute(
        '''SELECT genre, COUNT(*) as c FROM books
           WHERE user_id = ? AND shelf_status = ? AND genre != ''
           GROUP BY genre ORDER BY c DESC LIMIT 1''',
        (user_id, 'finished')
    ).fetchone()

    finished_this_year = db.execute(
        '''SELECT COUNT(*) as c FROM books
           WHERE user_id = ? AND shelf_status = ?
           AND strftime('%Y', date_finished) = '2026' ''',
        (user_id, 'finished')
    ).fetchone()['c']

    goal = db.execute(
        'SELECT * FROM goals WHERE user_id = ? AND target_year = 2026',
        (user_id,)
    ).fetchone()

    return render_template('stats/stats.html',
        total_books=total_books,
        total_pages=total_pages,
        avg_rating=avg_rating or 0,
        fav_genre=fav_genre['genre'] if fav_genre else 'none yet',
        finished_this_year=finished_this_year,
        goal=goal
    )


@app.route('/goal/set', methods=['POST'])
@login_required
def set_goal():
    target = request.form.get('target_book_count', '').strip()
    try:
        target = int(target)
        if target < 1 or target > 9999:
            raise ValueError
    except (ValueError, TypeError):
        return redirect(url_for('stats'))

    db = get_db()
    existing = db.execute(
        'SELECT * FROM goals WHERE user_id = ? AND target_year = 2026',
        (session['user_id'],)
    ).fetchone()
    if existing:
        db.execute(
            'UPDATE goals SET target_book_count = ? WHERE user_id = ? AND target_year = 2026',
            (target, session['user_id'])
        )
    else:
        db.execute(
            'INSERT INTO goals (user_id, target_year, target_book_count) VALUES (?, 2026, ?)',
            (session['user_id'], target)
        )
    db.commit()
    return redirect(url_for('stats'))

 
# PWA routes
 


@app.route('/sw.js')
def service_worker():
    response = app.make_response(app.send_static_file('js/sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/offline')
def offline():
    return render_template('offline.html')

 
# Error handlers
 

@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500

 
# Run
 

if __name__ == '__main__':
    database.init_db()
    app.run(debug=True)