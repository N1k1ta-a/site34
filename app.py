import os
import uuid
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, abort,
)
from werkzeug.utils import secure_filename
from models import db, Category, Item, User, Image
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

app = Flask(__name__)
app.secret_key = "secret-key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Настройки для загрузки файлов ---
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 МБ
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Убедимся, что папка существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

# --- Настройка Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Сначала войдите в систему'
login_manager.login_message_category = 'error'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

club_name = "RAVE by Buster"

# --- Вспомогательные функции для файлов ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file):
    if not file or file.filename == '':
        return None
    if not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f'{uuid.uuid4().hex}.{ext}'
    path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(path)
    return unique_name

# --- Декоратор для проверки прав администратора ---
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Доступ только для администратора', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper

# ==========================================
# СОЗДАНИЕ ТАБЛИЦ, АВТОЗАПОЛНЕНИЕ И АДМИН
# ==========================================
with app.app_context():
    db.create_all()

    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

    if not Category.query.first():
        cat_pc = Category(name="ПК-зоны")
        cat_console = Category(name="Консоли")
        cat_sim = Category(name="Симуляторы")
        db.session.add_all([cat_pc, cat_console, cat_sim])
        db.session.commit()

        items = [
            Item(title="Общий зал", description="80 ПК, BENQ ZOWIE 240Hz+.", available=True, category_id=cat_pc.id),
            Item(title="VIP-комната", description="600Hz, топовое железо.", available=False, category_id=cat_pc.id),
            Item(title="TRIO-комната", description="3 места, изолированная комната.", available=True, category_id=cat_pc.id),
            Item(title="PS5 зона", description="5 консолей PlayStation 5.", available=True, category_id=cat_console.id),
            Item(title="Автосимулятор", description="3 симулятора с рулём.", available=False, category_id=cat_sim.id),
        ]
        db.session.add_all(items)
        db.session.commit()

# ==========================================
# АУТЕНТИФИКАЦИЯ И ПРОФИЛЬ
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            flash("Заполните все поля", "error")
        elif len(username) < 3:
            flash("Логин должен быть не короче 3 символов", "error")
        elif len(password) < 6:
            flash("Пароль должен быть не короче 6 символов", "error")
        elif User.query.filter_by(username=username).first():
            flash("Этот логин уже занят", "error")
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("Регистрация успешна! Теперь войдите.", "success")
            return redirect(url_for("login"))
    return render_template("register.html", site_name=club_name)

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f"С возвращением, {user.username}!", "success")
            return redirect(url_for("index"))
        else:
            flash("Неверный логин или пароль", "error")
    return render_template("login.html", site_name=club_name)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))

@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user, site_name=club_name)

@app.route("/profile/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old_pass = request.form.get("old_password", "").strip()
        new_pass = request.form.get("new_password", "").strip()
        if not current_user.check_password(old_pass):
            flash("Неверный старый пароль", "error")
        elif len(new_pass) < 6:
            flash("Новый пароль должен быть не короче 6 символов", "error")
        else:
            current_user.set_password(new_pass)
            db.session.commit()
            flash("Пароль успешно изменён", "success")
            return redirect(url_for("profile"))
    return render_template("change_password.html", site_name=club_name)

@app.route("/users")
@login_required
@admin_required
def user_list():
    users = User.query.all()
    return render_template("user_list.html", users=users, site_name=club_name)

@app.route("/users/<int:user_id>/toggle-role", methods=["POST"])
@login_required
@admin_required
def toggle_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash("Нельзя менять роль главного администратора", "error")
    else:
        user.role = 'user' if user.role == 'admin' else 'admin'
        db.session.commit()
        flash(f"Роль пользователя {user.username} изменена на {user.role}", "success")
    return redirect(url_for("user_list"))

# ==========================================
# ЭЛЕМЕНТЫ И ЗОНЫ
# ==========================================

@app.route("/items")
def item_list():
    category_id = request.args.get('category', type=int)
    q = request.args.get('q', '').strip()
    query = Item.query
    if category_id: query = query.filter_by(category_id=category_id)
    if q: query = query.filter(Item.title.contains(q))
    items = query.all()
    categories = Category.query.all()
    return render_template('item_list.html', items=items, categories=categories, 
                           selected=category_id, q=q, site_name=club_name)

@app.route("/items/add", methods=["GET", "POST"])
@login_required
def item_add():
    categories = Category.query.all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        available = request.form.get("available") == "on"
        category_id = request.form.get("category_id")
        
        if not title:
            flash("Название обязательно", "error")
            return redirect(url_for("item_add"))

        # Сохранение главного изображения
        image_name = save_image(request.files.get('image'))
        if request.files.get('image') and not image_name:
            flash('Недопустимый формат файла (только png, jpg, jpeg, gif, webp)', "error")
            return redirect(url_for("item_add"))
            
        new_item = Item(title=title, description=description, available=available,
                        category_id=int(category_id) if category_id else None,
                        image=image_name)
        db.session.add(new_item)
        db.session.commit()

        # Сохранение галереи (несколько файлов)
        files = request.files.getlist('images')
        for file in files:
            name = save_image(file)
            if name:
                db.session.add(Image(filename=name, item_id=new_item.id))
        db.session.commit()

        flash(f"Зона «{title}» добавлена", "success")
        return redirect(url_for("item_list"))
        
    return render_template("item_form.html", categories=categories, site_name=club_name)

@app.route("/items/<int:item_id>")
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    return render_template("item_detail.html", item=item, site_name=club_name)

@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def item_edit(item_id):
    item = Item.query.get_or_404(item_id)
    categories = Category.query.all()
    if request.method == "POST":
        item.title = request.form.get("title", "").strip()
        item.description = request.form.get("description", "").strip()
        item.available = request.form.get("available") == "on"
        category_id = request.form.get("category_id")
        item.category_id = int(category_id) if category_id else None
        
        if not item.title:
            flash("Название обязательно", "error")
            return redirect(url_for("item_edit", item_id=item.id))

        # Замена главного изображения
        new_image = save_image(request.files.get('image'))
        if request.files.get('image') and not new_image:
            flash('Недопустимый формат файла', "error")
            return redirect(url_for("item_edit", item_id=item.id))
            
        if new_image:
            if item.image:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image)
                if os.path.exists(old_path):
                    os.remove(old_path)
            item.image = new_image

        # Добавление в галерею
        files = request.files.getlist('images')
        for file in files:
            name = save_image(file)
            if name:
                db.session.add(Image(filename=name, item_id=item.id))

        db.session.commit()
        flash("Зона обновлена", "success")
        return redirect(url_for("item_detail", item_id=item.id))
    return render_template("item_form.html", item=item, categories=categories, site_name=club_name)

@app.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
@admin_required
def item_delete(item_id):
    item = Item.query.get_or_404(item_id)
    
    # Удаление главной картинки с диска
    if item.image:
        path = os.path.join(app.config['UPLOAD_FOLDER'], item.image)
        if os.path.exists(path):
            os.remove(path)

    # Удаление картинок из галереи с диска
    for img in item.images:
        path = os.path.join(app.config['UPLOAD_FOLDER'], img.filename)
        if os.path.exists(path):
            os.remove(path)

    db.session.delete(item)
    db.session.commit()
    flash('Элемент удалён', 'success')
    return redirect(url_for('item_list'))

@app.route("/categories")
def category_list():
    categories = Category.query.all()
    return render_template("category_list.html", categories=categories, site_name=club_name)

@app.route("/categories/add", methods=["GET", "POST"])
@login_required
def category_add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Название категории обязательно", "error")
            return redirect(url_for("category_add"))
        if Category.query.filter_by(name=name).first():
            flash("Такая категория уже есть", "error")
            return redirect(url_for("category_add"))
        new_cat = Category(name=name)
        db.session.add(new_cat)
        db.session.commit()
        flash(f"Категория «{name}» добавлена", "success")
        return redirect(url_for("category_list"))
    return render_template("category_form.html", site_name=club_name)

# ==========================================
# ОБЫЧНЫЕ СТРАНИЦЫ, СТАРЫЕ ЗАДАНИЯ И ОШИБКИ
# ==========================================

@app.route("/")
def index():
    items = Item.query.all()
    return render_template("index.html", title="RAVE by Buster",
        description="Клуб, который построил Бустер. Москва, проспект Мира, 95. Заходи.",
        items=items, site_name=club_name)

@app.route("/about")
def about():
    return render_template("about.html", site_name=club_name)

@app.route("/contacts")
def contacts():
    return render_template("contacts.html", email="rave@buster.ru",
        phone="+7 (999) 190-45-95", address="Москва, проспект Мира, 95", site_name=club_name)

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    limit = request.args.get("limit", 10, type=int)
    category = request.args.get("category", "").strip()
    return render_template("search.html", q=q, limit=limit, category=category, site_name=club_name)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        message = request.form.get("message", "").strip()
        if not name:
            flash("Введите ник", "error")
            return redirect(url_for("feedback"))
        if len(message) < 5:
            flash("Сообщение слишком короткое", "error")
            return redirect(url_for("feedback"))
        flash(f"Спасибо, {name}!", "success")
        return redirect(url_for("feedback"))
    return render_template("feedback_form.html", site_name=club_name)

@app.route("/calc/<int:a>/<operation>/<int:b>")
def calc(a, operation, b):
    ops = {"add": a + b, "sub": a - b, "mul": a * b}
    if operation == "div":
        if b == 0: return "Ошибка: деление на ноль", 400
        return f"{a} / {b} = {a / b}"
    if operation not in ops: return f"Неизвестная операция: {operation}", 400
    return f"{a} {operation} {b} = {ops[operation]}"

@app.route("/go/<username>")
def go(username):
    return redirect(url_for("show_user", username=username))

@app.route("/user/<username>")
def show_user(username):
    return render_template("user.html", name=username, site_name=club_name)

# API JSON
api_items = [
    {"id": 1, "title": "Общий зал", "description": "80 ПК, 240Hz+"},
    {"id": 2, "title": "VIP-комната", "description": "600Hz, топовое железо"},
]

@app.route("/api/items", methods=["GET"])
def api_items_list():
    return jsonify(api_items), 200

@app.route("/api/item/<int:item_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
def api_item(item_id):
    global api_items
    item = next((i for i in api_items if i["id"] == item_id), None)
    if request.method == "GET":
        if item is None: return jsonify({"error": "Not found"}), 404
        return jsonify(item), 200
    if request.method == "PUT":
        if item is None: return jsonify({"error": "Not found"}), 404
        data = request.get_json(silent=True)
        if not data or "title" not in data or "description" not in data:
            return jsonify({"error": "title and description required"}), 400
        item["title"] = data["title"]
        item["description"] = data["description"]
        return jsonify(item), 200
    if request.method == "PATCH":
        if item is None: return jsonify({"error": "Not found"}), 404
        data = request.get_json(silent=True)
        if not data: return jsonify({"error": "No data"}), 400
        if "title" in data: item["title"] = data["title"]
        if "description" in data: item["description"] = data["description"]
        return jsonify(item), 200
    if request.method == "DELETE":
        if item is None: return jsonify({"error": "Not found"}), 404
        api_items = [i for i in api_items if i["id"] != item_id]
        return jsonify({"message": "Deleted"}), 200

@app.errorhandler(404)
def not_found(err):
    return render_template("404.html", site_name=club_name), 404

@app.errorhandler(405)
def method_not_allowed(err):
    return render_template("405.html", site_name=club_name), 405

@app.errorhandler(413)
def too_large(error):
    flash('Файл слишком большой (максимум 2 МБ)', 'error')
    return redirect(request.referrer or url_for('item_list'))

if __name__ == "__main__":
    app.run(debug=True)