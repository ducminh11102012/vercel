import os
import random
import logging
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from flask_mail import Mail, Message

# --- Logging Configuration ---
logging.basicConfig(filename='app.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

# --- App Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lottery.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Mail Configuration (sẽ được cập nhật từ DB) ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
# Các giá trị này sẽ được load từ DB trong hàm `update_mail_config`
app.config['MAIL_USERNAME'] = None
app.config['MAIL_PASSWORD'] = None
app.config['MAIL_DEFAULT_SENDER'] = None

db = SQLAlchemy(app)
mail = Mail(app)

# --- Admin Credentials (for demonstration purposes) ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

# --- Database Models ---
class Setting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=True)

class Draw(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prize_name = db.Column(db.String(100), nullable=False)
    draw_date = db.Column(db.DateTime, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=True)
    winning_number = db.Column(db.String(10), nullable=True)
    winner_email_content = db.Column(db.Text, nullable=True)
    participants = db.relationship('Participant', backref='draw', lazy=True, foreign_keys='Participant.draw_id', cascade="all, delete-orphan")
    winner = db.relationship('Participant', foreign_keys=[winner_id], post_update=True)

    @property
    def status(self):
        if self.winner:
            return 'Đã kết thúc'
        if datetime.now() > self.draw_date:
            return 'Đang quay số'
        return 'Sắp diễn ra'

class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    lucky_number = db.Column(db.String(10), nullable=False)
    ip_address = db.Column(db.String(45))
    draw_id = db.Column(db.Integer, db.ForeignKey('draw.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('email', 'draw_id', name='_email_draw_uc'),
                      db.UniqueConstraint('phone', 'draw_id', name='_phone_draw_uc'))


# --- Các mẫu HTML (Templates) ---
# Sử dụng Bootstrap 5 cho giao diện đẹp và nhanh chóng
TPL_BASE = """
<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Quay Số May Mắn{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f0f2f5; }
        .navbar { background-color: #fff; box-shadow: 0 2px 4px rgba(0,0,0,.1); }
        .card { border: none; box-shadow: 0 2px 8px rgba(0,0,0,.1); }
        .btn-primary { background-color: #0d6efd; border-color: #0d6efd; }
        .footer { background-color: #343a40; color: white; padding: 20px 0; }
        .status-badge { font-size: 0.9em; }
        .status-sap-dien-ra { background-color: #ffc107 !important; color: #000 !important; }
        .status-da-ket-thuc { background-color: #6c757d !important; }
        .status-dang-quay-so { background-color: #dc3545 !important; }
        .winner-row { background-color: #d1e7dd !important; font-weight: bold; }
        .log-error { color: red; font-family: monospace; }
        .log-info { color: black; font-family: monospace; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light mb-4">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('index') }}">🎁 Quay Số VPS Free</a>
            {% if session.get('is_admin') %}
            <div class="ms-auto">
                <a class="nav-link d-inline-block me-3" href="{{ url_for('admin_dashboard') }}">Dashboard</a>
                <a class="nav-link d-inline-block me-3" href="{{ url_for('admin_settings') }}">Cài đặt</a>
                <a class="nav-link d-inline-block" href="{{ url_for('view_logs') }}">Logs</a>
            </div>
            {% endif %}
        </div>
    </nav>
    <main class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
    <footer class="footer mt-5 text-center">
        <p>&copy; {{ now.year }} - Nền tảng quay số may mắn.</p>
    </footer>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
"""

TPL_INDEX = TPL_BASE.replace('{% block content %}{% endblock %}', """
<div class="text-center mb-5">
    <h1>Các Đợt Quay Số</h1>
    <p class="lead">Tham gia ngay để có cơ hội nhận VPS miễn phí hàng tháng!</p>
</div>
<div class="row">
    {% for draw in draws %}
    <div class="col-md-6 col-lg-4 mb-4">
        <div class="card h-100">
            <div class="card-body d-flex flex-column">
                <h5 class="card-title">{{ draw.prize_name }}</h5>
                <p class="card-text text-muted">Ngày quay: {{ draw.draw_date.strftime('%d/%m/%Y lúc %H:%M') }}</p>
                <div class="mt-auto">
                    <span class="badge status-badge 
                        {% if draw.status == 'Sắp diễn ra' %}status-sap-dien-ra
                        {% elif draw.status == 'Đã kết thúc' %}status-da-ket-thuc
                        {% elif draw.status == 'Đang quay số' %}status-dang-quay-so
                        {% endif %}">
                        {{ draw.status }}
                    </span>
                    {% if draw.status == 'Sắp diễn ra' %}
                        <a href="{{ url_for('register', draw_id=draw.id) }}" class="btn btn-primary float-end">Đăng Ký</a>
                    {% elif draw.status == 'Đang quay số' %}
                         <a href="{{ url_for('spin', draw_id=draw.id) }}" class="btn btn-danger float-end">Xem Quay Số</a>
                    {% elif draw.status == 'Đã kết thúc' and draw.winner %}
                        <p class="mt-2 mb-0">Chúc mừng: <strong>{{ draw.winner.full_name }}</strong></p>
                        <p class="mb-0">Số may mắn: <strong>{{ draw.winning_number }}</strong></p>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
    {% else %}
    <div class="col">
        <p class="text-center">Chưa có đợt quay số nào được tạo. Vui lòng quay lại sau.</p>
    </div>
    {% endfor %}
</div>
""")

TPL_REGISTER = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Đăng Ký Tham Gia').replace('{% block content %}{% endblock %}', """
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-body">
                <h3 class="card-title text-center">Đăng Ký Nhận {{ draw.prize_name }}</h3>
                <p class="text-center text-muted">Ngày quay: {{ draw.draw_date.strftime('%d/%m/%Y lúc %H:%M') }}</p>
                <form method="POST">
                    <div class="mb-3">
                        <label for="full_name" class="form-label">Họ và Tên</label>
                        <input type="text" class="form-control" id="full_name" name="full_name" required>
                    </div>
                    <div class="mb-3">
                        <label for="phone" class="form-label">Số Điện Thoại</label>
                        <input type="tel" class="form-control" id="phone" name="phone" required>
                    </div>
                    <div class="mb-3">
                        <label for="email" class="form-label">Email</label>
                        <input type="email" class="form-control" id="email" name="email" required>
                    </div>
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary btn-lg">Gửi Đăng Ký</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
""")

TPL_THANK_YOU = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Đăng Ký Thành Công').replace('{% block content %}{% endblock %}', """
<div class="text-center">
    <div class="card mx-auto" style="max-width: 400px;">
        <div class="card-body">
            <h2 class="card-title">🎉 Cảm ơn bạn đã tham gia! 🎉</h2>
            <p class="lead">Chúc bạn may mắn. Số thứ tự quay của bạn là:</p>
            <h1 class="display-4 my-4 p-3 bg-light rounded">{{ lucky_number }}</h1>
            <a href="{{ url_for('index') }}" class="btn btn-secondary">Quay về trang chủ</a>
        </div>
    </div>
</div>
""")

TPL_SPIN_PAGE = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Vòng Quay May Mắn').replace('{% block content %}{% endblock %}', """
{% block content %}
<div class="container text-center">
    <h1>Vòng Quay May Mắn - {{ draw.prize_name }}</h1>
    <p class="lead">Vòng quay sẽ tự động bắt đầu. Chúc bạn may mắn!</p>
    
    <div id="wheel" class="my-4" style="font-size: 5rem; font-weight: bold; background-color: #e9ecef; padding: 40px; border-radius: 20px;">
        <span id="number-display">00000</span>
    </div>

    <div id="result" class="d-none">
        <h2>🎉 Chúc Mừng Người Thắng Cuộc! 🎉</h2>
        <p>Số may mắn là: <strong id="winning-number" class="fs-3"></strong></p>
        <p>Họ tên: <strong id="winner-name"></strong></p>
        <p>Số điện thoại: <strong id="winner-phone"></strong></p>
        <p class="text-success">Vui lòng kiểm tra email để nhận thông tin giải thưởng!</p>
        <a href="{{ url_for('index') }}" class="btn btn-primary mt-3">Xem các đợt quay khác</a>
    </div>
</div>
{% endblock %}
""").replace('{% block scripts %}{% endblock %}', """
{% block scripts %}
<script>
    document.addEventListener('DOMContentLoaded', function() {
        const numberDisplay = document.getElementById('number-display');
        const resultDiv = document.getElementById('result');
        const wheelDiv = document.getElementById('wheel');
        let spinningInterval;

        function startSpinning() {
            spinningInterval = setInterval(() => {
                const randomNum = Math.floor(10000 + Math.random() * 90000).toString();
                numberDisplay.textContent = randomNum;
            }, 80);
        }

        function stopSpinningAndShowWinner(winnerData) {
            clearInterval(spinningInterval);
            numberDisplay.textContent = winnerData.winning_number;
            
            document.getElementById('winning-number').textContent = winnerData.winning_number;
            document.getElementById('winner-name').textContent = winnerData.winner_name;
            document.getElementById('winner-phone').textContent = winnerData.winner_phone;

            wheelDiv.classList.add('d-none');
            resultDiv.classList.remove('d-none');
        }

        function handleNoWinner() {
            clearInterval(spinningInterval);
            numberDisplay.textContent = "---";
            alert("Không có người tham gia trong vòng quay này hoặc đã có lỗi xảy ra.");
            window.location.href = "{{ url_for('index') }}";
        }

        function fetchWinner() {
            fetch("{{ url_for('get_winner', draw_id=draw.id) }}")
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        handleNoWinner();
                    } else {
                        // Đợi một chút để người dùng thấy số trúng thưởng cuối cùng
                        setTimeout(() => stopSpinningAndShowWinner(data), 1000);
                    }
                })
                .catch(error => {
                    console.error('Error fetching winner:', error);
                    handleNoWinner();
                });
        }

        // Bắt đầu quay ngay lập tức
        startSpinning();

        // Sau 5 giây, gọi API để lấy người thắng cuộc
        setTimeout(fetchWinner, 5000); // Quay trong 5 giây
    });
</script>
{% endblock %}
""")
# --- Mẫu HTML cho trang quản trị ---
TPL_LOGIN = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Đăng Nhập Quản Trị').replace('{% block content %}{% endblock %}', """
{% block content %}
<div class="row justify-content-center mt-5">
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <h3 class="card-title text-center">Đăng Nhập Administrator</h3>
                <form method="POST">
                    <div class="mb-3">
                        <label for="username" class="form-label">Tên đăng nhập</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">Mật khẩu</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                     <div class="d-grid">
                        <button type="submit" class="btn btn-primary">Đăng Nhập</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
""")

TPL_ADMIN_DASHBOARD = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Bảng Điều Khiển').replace('{% block content %}{% endblock %}', """
<div class="d-flex justify-content-between align-items-center mb-4">
    <h1>Bảng Điều Khiển</h1>
    <div>
        <a href="{{ url_for('logout') }}" class="btn btn-secondary">Đăng Xuất</a>
    </div>
</div>

<div class="card mb-4">
    <div class="card-header">
        Tạo Đợt Quay Số Mới
    </div>
    <div class="card-body">
        <form action="{{ url_for('create_draw') }}" method="POST">
            <div class="row g-3">
                <div class="col-md-6">
                    <label for="prize_name" class="form-label">Tên Giải Thưởng</label>
                    <input type="text" class="form-control" id="prize_name" name="prize_name" required>
                </div>
                <div class="col-md-3">
                    <label for="draw_date" class="form-label">Ngày Quay</label>
                    <input type="date" class="form-control" id="draw_date" name="draw_date" required>
                </div>
                <div class="col-md-3">
                    <label for="draw_time" class="form-label">Giờ Quay</label>
                    <input type="time" class="form-control" id="draw_time" name="draw_time" required>
                </div>
                <div class="col-12">
                    <label for="winner_email_content" class="form-label">Nội dung Email cho người trúng (Tùy chọn)</label>
                    <textarea class="form-control" id="winner_email_content" name="winner_email_content" rows="3" placeholder="Sử dụng các biến: {{full_name}}, {{phone}}, {{email}}, {{prize_name}}, {{lucky_number}}. Ví dụ: Chúc mừng {{full_name}} đã trúng giải {{prize_name}}. Chúng tôi sẽ liên hệ với bạn qua SĐT {{phone}} để trao giải."></textarea>
                </div>
                <div class="col-12">
                    <button type="submit" class="btn btn-primary">Tạo Mới</button>
                </div>
            </div>
        </form>
    </div>
</div>

<div class="card">
    <div class="card-header">
        Danh Sách Các Đợt Quay Số
    </div>
    <div class="card-body">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Giải Thưởng</th>
                    <th>Ngày Quay</th>
                    <th>Trạng Thái</th>
                    <th>Số người tham gia</th>
                    <th>Hành động</th>
                </tr>
            </thead>
            <tbody>
                {% for draw in draws %}
                <tr>
                    <td>{{ draw.id }}</td>
                    <td>{{ draw.prize_name }}</td>
                    <td>{{ draw.draw_date.strftime('%d/%m/%Y %H:%M') }}</td>
                    <td><span class="badge 
                        {% if draw.status == 'Sắp diễn ra' %}bg-warning text-dark
                        {% elif draw.status == 'Đã kết thúc' %}bg-secondary
                        {% else %}bg-danger{% endif %}">{{ draw.status }}</span>
                    </td>
                    <td>{{ draw.participants|length }}</td>
                    <td>
                        <a href="{{ url_for('view_participants', draw_id=draw.id) }}" class="btn btn-sm btn-info">Xem DS</a>
                        <a href="{{ url_for('delete_draw', draw_id=draw.id) }}" class="btn btn-sm btn-danger" onclick="return confirm('Bạn có chắc chắn muốn xóa đợt quay số này không? Thao tác này sẽ xóa cả người tham gia.');">Xóa</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
""")

TPL_ADMIN_PARTICIPANTS = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Danh Sách Tham Gia').replace('{% block content %}{% endblock %}', """
<div class="d-flex justify-content-between align-items-center mb-4">
    <div>
        <h1>Danh sách tham gia - {{ draw.prize_name }}</h1>
        {% if draw.winner %}
            <p class="lead">Người thắng cuộc: <strong>{{ draw.winner.full_name }}</strong> (SĐT: {{ draw.winner.phone }}, Email: {{ draw.winner.email }})</p>
        {% endif %}
    </div>
    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-secondary align-self-start">Quay lại</a>
</div>

{% if draw.winner and draw.winner_email_content %}
<div class="card mb-4">
    <div class="card-body d-flex justify-content-between align-items-center">
        <span>Gửi email thông báo cho người thắng cuộc.</span>
        <a href="{{ url_for('send_winner_email', draw_id=draw.id) }}" class="btn btn-success">Gửi Email Ngay</a>
    </div>
</div>
{% endif %}

<div class="card">
    <div class="card-body">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>Họ Tên</th>
                    <th>Email</th>
                    <th>SĐT</th>
                    <th>Số May Mắn</th>
                    <th>Địa chỉ IP</th>
                </tr>
            </thead>
            <tbody>
                {% for p in participants %}
                <tr class="{{ 'winner-row' if p.id == draw.winner_id }}">
                    <td>{{ p.full_name }}</td>
                    <td>{{ p.email }}</td>
                    <td>{{ p.phone }}</td>
                    <td>{{ p.lucky_number }}</td>
                    <td>{{ p.ip_address }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
""")

TPL_ADMIN_SETTINGS = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Cài Đặt').replace('{% block content %}{% endblock %}', """
<div class="row justify-content-center">
    <div class="col-md-8">
        <div class="card">
            <div class="card-header">
                <h3>Cài đặt gửi Email (Gmail)</h3>
            </div>
            <div class="card-body">
                <p class="text-muted">Sử dụng 'Mật khẩu ứng dụng' của Google nếu bạn đã bật Xác minh 2 bước.</p>
                <form method="POST">
                    <div class="mb-3">
                        <label for="mail_username" class="form-label">Email người gửi (Gmail)</label>
                        <input type="email" class="form-control" id="mail_username" name="mail_username" value="{{ settings.get('MAIL_USERNAME', '') }}" required>
                    </div>
                    <div class="mb-3">
                        <label for="mail_password" class="form-label">Mật khẩu ứng dụng</label>
                        <input type="password" class="form-control" id="mail_password" name="mail_password" value="{{ settings.get('MAIL_PASSWORD', '') }}" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Lưu Cài Đặt</button>
                    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-secondary">Hủy</a>
                </form>
            </div>
        </div>
    </div>
</div>
""")

TPL_LOGS = TPL_BASE.replace('{% block title %}Quay Số May Mắn{% endblock %}', 'Logs Hệ Thống').replace('{% block content %}{% endblock %}', """
<div class="d-flex justify-content-between align-items-center mb-4">
    <h1>Logs Hệ Thống</h1>
    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-secondary">Quay lại</a>
</div>
<div class="card">
    <div class="card-body">
        <pre style="white-space: pre-wrap; word-wrap: break-word;">
        {% for line in log_lines %}
            {% if 'ERROR' in line %}
                <span class="log-error">{{ line }}</span>
            {% else %}
                <span class="log-info">{{ line }}</span>
            {% endif %}
        {% else %}
            <p>Chưa có log nào.</p>
        {% endfor %}
        </pre>
    </div>
</div>
""")


# --- Helper Functions ---
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

def update_mail_config():
    """Load mail settings from DB and update app.config."""
    with app.app_context():
        mail_username = Setting.query.get('MAIL_USERNAME')
        mail_password = Setting.query.get('MAIL_PASSWORD')
        if mail_username and mail_password:
            app.config['MAIL_USERNAME'] = mail_username.value
            app.config['MAIL_PASSWORD'] = mail_password.value
            app.config['MAIL_DEFAULT_SENDER'] = mail_username.value
            mail.init_app(app) # Re-initialize mail with new config

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Bạn cần đăng nhập với quyền admin để truy cập trang này.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Public Routes ---
@app.route('/')
def index():
    draws = Draw.query.order_by(Draw.draw_date.desc()).all()
    return render_template_string(TPL_INDEX, draws=draws)

@app.route('/register/<int:draw_id>', methods=['GET', 'POST'])
def register(draw_id):
    draw = Draw.query.get_or_404(draw_id)
    if draw.status != 'Sắp diễn ra':
        flash('Đợt quay số này không còn mở để đăng ký.', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        email = request.form['email']

        # Check for duplicates
        if Participant.query.filter_by(draw_id=draw.id, email=email).first() or \
           Participant.query.filter_by(draw_id=draw.id, phone=phone).first():
            flash('Email hoặc Số điện thoại này đã được đăng ký cho đợt quay số này.', 'danger')
            return render_template_string(TPL_REGISTER, draw=draw)

        # Generate a unique lucky number
        while True:
            lucky_number = str(random.randint(10000, 99999))
            if not Participant.query.filter_by(draw_id=draw.id, lucky_number=lucky_number).first():
                break
        
        participant = Participant(
            full_name=full_name,
            phone=phone,
            email=email,
            lucky_number=lucky_number,
            ip_address=request.remote_addr,
            draw_id=draw.id
        )
        db.session.add(participant)
        db.session.commit()
        
        return render_template_string(TPL_THANK_YOU, lucky_number=lucky_number)

    return render_template_string(TPL_REGISTER, draw=draw)

@app.route('/spin/<int:draw_id>')
def spin(draw_id):
    draw = Draw.query.get_or_404(draw_id)
    if draw.status == 'Sắp diễn ra':
        flash('Vòng quay chưa bắt đầu.', 'info')
        return redirect(url_for('index'))
    return render_template_string(TPL_SPIN_PAGE, draw=draw)

@app.route('/get-winner/<int:draw_id>')
def get_winner(draw_id):
    draw = Draw.query.get_or_404(draw_id)

    if draw.winner:
        return jsonify({
            'winner_name': draw.winner.full_name,
            'winner_phone': draw.winner.phone,
            'winning_number': draw.winning_number
        })

    participants = draw.participants
    if not participants:
        return jsonify({'error': 'No participants'}), 404

    winner = random.choice(participants)
    draw.winner_id = winner.id
    draw.winning_number = winner.lucky_number
    db.session.commit()
    logging.info(f"Draw '{draw.prize_name}' (ID: {draw.id}) has a winner: {winner.full_name} (ID: {winner.id}) with number {winner.lucky_number}.")

    return jsonify({
        'winner_name': winner.full_name,
        'winner_phone': winner.phone,
        'winning_number': winner.lucky_number
    })

# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
def login():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('Đăng nhập thành công!', 'success')
            logging.info("Admin logged in successfully.")
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'danger')
            logging.warning(f"Failed admin login attempt for username: {username}.")
    return render_template_string(TPL_LOGIN)

@app.route('/admin/logout')
def logout():
    session.pop('is_admin', None)
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    draws = Draw.query.order_by(Draw.draw_date.desc()).all()
    return render_template_string(TPL_ADMIN_DASHBOARD, draws=draws)

@app.route('/admin/create_draw', methods=['POST'])
@admin_required
def create_draw():
    prize_name = request.form['prize_name']
    draw_date_str = request.form['draw_date']
    draw_time_str = request.form['draw_time']
    email_content = request.form.get('winner_email_content')

    draw_datetime = datetime.strptime(f"{draw_date_str} {draw_time_str}", '%Y-%m-%d %H:%M')

    new_draw = Draw(
        prize_name=prize_name,
        draw_date=draw_datetime,
        winner_email_content=email_content
    )
    db.session.add(new_draw)
    db.session.commit()
    flash(f'Đã tạo thành công đợt quay số "{prize_name}".', 'success')
    logging.info(f"Admin created a new draw: '{prize_name}' (ID: {new_draw.id}).")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/participants/<int:draw_id>')
@admin_required
def view_participants(draw_id):
    draw = Draw.query.get_or_404(draw_id)
    participants = sorted(draw.participants, key=lambda p: p.id)
    return render_template_string(TPL_ADMIN_PARTICIPANTS, draw=draw, participants=participants)

@app.route('/admin/delete_draw/<int:draw_id>', methods=['GET'])
@admin_required
def delete_draw(draw_id):
    draw = Draw.query.get_or_404(draw_id)
    prize_name = draw.prize_name
    # Cascade delete is configured on the relationship, so this is simpler.
    db.session.delete(draw)
    db.session.commit()
    flash(f'Đã xóa đợt quay số "{prize_name}" và tất cả người tham gia.', 'success')
    logging.info(f"Admin deleted draw '{prize_name}' (ID: {draw_id}).")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        # Update or create MAIL_USERNAME
        username_setting = Setting.query.get('MAIL_USERNAME')
        if not username_setting:
            username_setting = Setting(key='MAIL_USERNAME')
            db.session.add(username_setting)
        username_setting.value = request.form['mail_username']

        # Update or create MAIL_PASSWORD
        password_setting = Setting.query.get('MAIL_PASSWORD')
        if not password_setting:
            password_setting = Setting(key='MAIL_PASSWORD')
            db.session.add(password_setting)
        password_setting.value = request.form['mail_password']
        
        db.session.commit()
        update_mail_config() # Cập nhật config ngay lập tức
        flash('Cài đặt email đã được lưu.', 'success')
        logging.info("Admin updated mail settings.")
        return redirect(url_for('admin_settings'))

    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template_string(TPL_ADMIN_SETTINGS, settings=settings)

@app.route('/admin/logs')
@admin_required
def view_logs():
    try:
        with open('app.log', 'r', encoding='utf-8') as f:
            # Đọc ngược file để log mới nhất ở trên
            log_lines = f.readlines()[::-1]
    except FileNotFoundError:
        log_lines = []
    return render_template_string(TPL_LOGS, log_lines=log_lines)

@app.route('/admin/send_email/<int:draw_id>')
@admin_required
def send_winner_email(draw_id):
    draw = Draw.query.get_or_404(draw_id)
    if not draw.winner:
        flash('Đợt quay này chưa có người thắng cuộc.', 'warning')
        return redirect(url_for('view_participants', draw_id=draw_id))

    if not app.config.get('MAIL_USERNAME'):
        flash('Vui lòng cấu hình email trong trang Cài đặt trước khi gửi.', 'danger')
        return redirect(url_for('admin_settings'))

    winner = draw.winner
    subject = f"Chúc mừng bạn đã trúng giải: {draw.prize_name}"
    
    # Thay thế các biến trong nội dung email
    body = draw.winner_email_content.replace("{{full_name}}", winner.full_name)
    body = body.replace("{{phone}}", winner.phone)
    body = body.replace("{{email}}", winner.email)
    body = body.replace("{{prize_name}}", draw.prize_name)
    body = body.replace("{{lucky_number}}", winner.lucky_number)

    msg = Message(subject, recipients=[winner.email], body=body)
    
    try:
        mail.send(msg)
        flash(f'Đã gửi email thành công tới {winner.email}.', 'success')
        logging.info(f"Successfully sent winner email for draw '{draw.prize_name}' to {winner.email}.")
    except Exception as e:
        flash(f'Gửi email thất bại: {e}', 'danger')
        logging.error(f"ERROR sending winner email for draw '{draw.prize_name}' to {winner.email}. Details: {e}")

    return redirect(url_for('view_participants', draw_id=draw_id))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        update_mail_config()
    import os
    port = int(os.environ.get("PORT", 5000))  # lấy port từ môi trường
    app.run(host="0.0.0.0", port=port, debug=True)  # host=0.0.0.0 để cloud truy cập

