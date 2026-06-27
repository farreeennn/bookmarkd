-- Bookmarkd Database Schema
-- SQLite3

CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT NOT NULL,
    email            TEXT NOT NULL UNIQUE,
    hashed_password  TEXT NOT NULL,
    display_name     TEXT NOT NULL,
    date_registered  TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS books (
    book_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    title          TEXT NOT NULL,
    author         TEXT NOT NULL,
    genre          TEXT DEFAULT '',
    shelf_status   TEXT NOT NULL DEFAULT 'want_to_read',
    total_pages    INTEGER,
    current_page   INTEGER DEFAULT 0,
    date_started   TEXT,
    date_finished  TEXT,
    cover_url      TEXT DEFAULT '',
    is_favourite   INTEGER DEFAULT 0,
    personal_notes TEXT DEFAULT '',
    dnf_note       TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id      INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    star_rating  INTEGER NOT NULL CHECK(star_rating BETWEEN 1 AND 5),
    review_text  TEXT DEFAULT '',
    date_written TEXT DEFAULT (date('now')),
    FOREIGN KEY (book_id) REFERENCES books(book_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS goals (
    goal_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    target_year       INTEGER NOT NULL,
    target_book_count INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS diary_entries (
    entry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    book_id      INTEGER,
    entry_text   TEXT NOT NULL,
    date_created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (book_id) REFERENCES books(book_id)
);