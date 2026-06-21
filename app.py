import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'bookhole_super_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('bookhole.db')
    conn.row_factory = sqlite3.Row
    return conn

# 自動建立討論區相關資料表與升級遷移
def init_discussion_tables():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            UNIQUE(title, author)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Discussions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER,
            user_id INTEGER,
            title TEXT,
            author TEXT,
            viewpoint TEXT,
            created_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discussion_id INTEGER,
            user_id INTEGER,
            content TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    
    try:
        conn.execute('SELECT book_id FROM Discussions LIMIT 1')
    except sqlite3.OperationalError:
        conn.execute('ALTER TABLE Discussions ADD COLUMN book_id INTEGER')
        conn.commit()

    old_discs = conn.execute('SELECT id, title, author FROM Discussions WHERE book_id IS NULL').fetchall()
    for row in old_discs:
        book = conn.execute('SELECT id FROM Books WHERE title = ? AND (author = ? OR (author IS NULL AND ? IS NULL))', 
                            (row['title'], row['author'], row['author'])).fetchone()
        if book:
            b_id = book['id']
        else:
            cursor = conn.execute('INSERT INTO Books (title, author) VALUES (?, ?)', (row['title'], row['author']))
            b_id = cursor.lastrowid
        conn.execute('UPDATE Discussions SET book_id = ? WHERE id = ?', (b_id, row['id']))
    
    conn.commit()
    conn.close()

# 自動為 Users 資料表擴充 TOP 3 獨立書本封面欄位
def init_user_top_books():
    conn = get_db_connection()
    try:
        conn.execute('SELECT top1_img FROM Users LIMIT 1')
    except sqlite3.OperationalError:
        conn.execute('ALTER TABLE Users ADD COLUMN top1_img TEXT')
        conn.execute('ALTER TABLE Users ADD COLUMN top2_img TEXT')
        conn.execute('ALTER TABLE Users ADD COLUMN top3_img TEXT')
        conn.commit()
    conn.close()

init_discussion_tables()
init_user_top_books()

# ===== 登入與註冊 =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        if action == 'register':
            existing = conn.execute('SELECT * FROM Users WHERE username = ?', (username,)).fetchone()
            if existing:
                return "此帳號已存在，請換一個名稱或直接登入。"
            hashed_pw = generate_password_hash(password)
            cursor = conn.execute('INSERT INTO Users (username, password_hash) VALUES (?, ?)', (username, hashed_pw))
            conn.commit()
            session['user_id'] = cursor.lastrowid
        elif action == 'login':
            user = conn.execute('SELECT * FROM Users WHERE username = ?', (username,)).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
            else:
                return "帳號或密碼錯誤！"
        conn.close()
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

# ===== 核心頁面 =====
@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        bio = request.form.get('bio')
        fav_book = request.form.get('fav_book')
        quote = request.form.get('quote')
        
        avatar = request.files.get('avatar')
        if avatar and avatar.filename != '':
            avatar_filename = avatar.filename
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))
            conn.execute('UPDATE Users SET avatar_url = ? WHERE id = ?', (avatar_filename, session['user_id']))
            
        conn.execute('''
            UPDATE Users SET nickname = ?, bio = ?, fav_book = ?, quote = ? WHERE id = ?
        ''', (nickname, bio, fav_book, quote, session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('profile'))

    user = conn.execute('SELECT * FROM Users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    
    # 這裡已經不需要再抓 Library 的書了，因為我們有獨立的欄位
    return render_template('profile.html', user=user)

# 專門更新個人主頁 TOP 3 書籍封面的獨立路由
@app.route('/update_top_book/<int:slot>', methods=['POST'])
def update_top_book(slot):
    if 'user_id' not in session: return redirect(url_for('login'))
    if slot not in [1, 2, 3]: return redirect(url_for('profile'))

    img_file = request.files.get('top_book_img')
    if img_file and img_file.filename != '':
        img_filename = img_file.filename
        img_file.save(os.path.join(app.config['UPLOAD_FOLDER'], img_filename))

        conn = get_db_connection()
        # 動態指定更新 top1_img, top2_img 還是 top3_img
        column_name = f'top{slot}_img'
        conn.execute(f'UPDATE Users SET {column_name} = ? WHERE id = ?', (img_filename, session['user_id']))
        conn.commit()
        conn.close()

    return redirect(url_for('profile'))

@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session: return redirect(url_for('login'))
    new_password = request.form.get('new_password')
    if new_password:
        conn = get_db_connection()
        hashed_pw = generate_password_hash(new_password)
        conn.execute('UPDATE Users SET password_hash = ? WHERE id = ?', (hashed_pw, session['user_id']))
        conn.commit()
        conn.close()
    return redirect(url_for('profile'))

# ===== 書庫管理 =====
@app.route('/library', methods=['GET', 'POST'])
def library():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        review = request.form.get('review')
        cover_img = request.files.get('cover_img')
        img_filename = None
        if cover_img and cover_img.filename != '':
            img_filename = cover_img.filename
            cover_img.save(os.path.join(app.config['UPLOAD_FOLDER'], img_filename))
            
        conn.execute('INSERT INTO Library (user_id, title, author, review, cover_img_url) VALUES (?, ?, ?, ?, ?)', 
                     (session['user_id'], title, author, review, img_filename))
        conn.commit()
        return redirect(url_for('library'))

    books = conn.execute('SELECT * FROM Library WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('library.html', books=books)

@app.route('/edit_book/<int:book_id>', methods=['POST'])
def edit_book(book_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    title = request.form.get('title')
    author = request.form.get('author')
    review = request.form.get('review')
    cover_img = request.files.get('cover_img')
    
    conn = get_db_connection()
    
    if cover_img and cover_img.filename != '':
        img_filename = cover_img.filename
        cover_img.save(os.path.join(app.config['UPLOAD_FOLDER'], img_filename))
        conn.execute('UPDATE Library SET title=?, author=?, review=?, cover_img_url=? WHERE id=? AND user_id=?', 
                     (title, author, review, img_filename, book_id, session['user_id']))
    else:
        conn.execute('UPDATE Library SET title=?, author=?, review=? WHERE id=? AND user_id=?', 
                     (title, author, review, book_id, session['user_id']))
                     
    conn.commit()
    conn.close()
    return redirect(url_for('library'))

# 新增：刪除書籍的路由
@app.route('/delete_book/<int:book_id>')
def delete_book(book_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    # 確保只有該書籍的擁有者才能刪除
    conn.execute('DELETE FROM Library WHERE id = ? AND user_id = ?', (book_id, session['user_id']))
    conn.commit()
    conn.close()
    
    return redirect(url_for('library'))

# ===== 好書推薦 =====
@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        conn.execute('INSERT INTO Recommendations (title, author, added_by) VALUES (?, ?, ?)',
                     (title, author, session['user_id']))
        conn.commit()
        return redirect(url_for('recommend'))
        
    query = '''
        SELECT r.*, u.nickname AS referrer_name, u.username AS referrer_username, u.avatar_url AS referrer_avatar,
               COUNT(v.id) AS vote_count
        FROM Recommendations r
        LEFT JOIN Users u ON r.added_by = u.id
        LEFT JOIN Recommendation_Votes v ON r.id = v.rec_id
        GROUP BY r.id
        ORDER BY vote_count DESC, r.id DESC
    '''
    recs = conn.execute(query).fetchall()
    conn.close()
    return render_template('recommend.html', recs=recs)

@app.route('/vote_recommend/<int:rec_id>', methods=['POST'])
def vote_recommend(rec_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO Recommendation_Votes (rec_id, user_id) VALUES (?, ?)', (rec_id, session['user_id']))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()
    return redirect(url_for('recommend'))

# ===== 三層結構書籍討論區 =====
@app.route('/discussion', methods=['GET', 'POST'])
def discussion():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    if request.method == 'POST':
        book_id = request.form.get('book_id')
        viewpoint = request.form.get('viewpoint')
        current_time = datetime.now().strftime('%m/%d %H:%M')
        
        if book_id:
            book = conn.execute('SELECT title, author FROM Books WHERE id = ?', (book_id,)).fetchone()
            conn.execute('INSERT INTO Discussions (book_id, user_id, title, author, viewpoint, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                         (book_id, session['user_id'], book['title'], book['author'], viewpoint, current_time))
        else:
            title = request.form.get('title')
            author = request.form.get('author')
            
            book = conn.execute('SELECT id FROM Books WHERE title = ? AND (author = ? OR (author IS NULL AND ? IS NULL))', 
                                (title, author, author)).fetchone()
            if book:
                b_id = book['id']
            else:
                cursor = conn.execute('INSERT INTO Books (title, author) VALUES (?, ?)', (title, author))
                b_id = cursor.lastrowid
                
            conn.execute('INSERT INTO Discussions (book_id, user_id, title, author, viewpoint, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                         (b_id, session['user_id'], title, author, viewpoint, current_time))
            
        conn.commit()
        conn.close()
        return redirect(url_for('discussion'))
        
    book_rows = conn.execute('SELECT * FROM Books ORDER BY id DESC').fetchall()
    books = []
    
    for b_row in book_rows:
        b_dict = dict(b_row)
        discs = conn.execute('''
            SELECT d.*, u.nickname, u.username 
            FROM Discussions d
            LEFT JOIN Users u ON d.user_id = u.id
            WHERE d.book_id = ?
            ORDER BY d.id DESC
        ''', (b_dict['id'],)).fetchall()
        
        discussions_list = []
        for d_row in discs:
            d_dict = dict(d_row)
            comments = conn.execute('''
                SELECT c.*, u.nickname, u.username, u.avatar_url
                FROM Comments c
                LEFT JOIN Users u ON c.user_id = u.id
                WHERE c.discussion_id = ?
                ORDER BY c.id ASC
            ''', (d_dict['id'],)).fetchall()
            d_dict['comments'] = comments
            discussions_list.append(d_dict)
            
        b_dict['discussions'] = discussions_list
        books.append(b_dict)
        
    conn.close()
    return render_template('discussion.html', books=books)

@app.route('/add_comment/<int:discussion_id>', methods=['POST'])
def add_comment(discussion_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    content = request.form.get('content')
    if content:
        conn = get_db_connection()
        current_time = datetime.now().strftime('%m/%d %H:%M')
        conn.execute('INSERT INTO Comments (discussion_id, user_id, content, created_at) VALUES (?, ?, ?, ?)',
                     (discussion_id, session['user_id'], content, current_time))
        conn.commit()
        conn.close()
    return redirect(url_for('discussion'))

@app.route('/edit_comment/<int:comment_id>', methods=['POST'])
def edit_comment(comment_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    new_content = request.form.get('content')
    if new_content:
        conn = get_db_connection()
        conn.execute('UPDATE Comments SET content = ? WHERE id = ? AND user_id = ?',
                     (new_content, comment_id, session['user_id']))
        conn.commit()
        conn.close()
    return redirect(url_for('discussion'))

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM Comments WHERE id = ? AND user_id = ?', (comment_id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('discussion'))

if __name__ == '__main__':
    app.run(debug=True)
