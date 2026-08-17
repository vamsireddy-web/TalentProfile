import profile

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, TalentProfile
from functools import wraps
import os, bcrypt, secrets, tempfile

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///talent.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Admin decorator to restrict access to admin users
def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', '403')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped

# Token store for password reset tokens
reset_tokens = {}

#------Create the database tables if they don't exist------
with app.app_context():
    db.create_all()
    print("Database tables created.")


    #================================================================================================
    # AUTHORIZATION ROUTES
    #================================================================================================   

    @app.route('/')
    def index():
        return redirect(url_for('browse'))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')  
            
       # Validate form inputs     
            errors = []
            if not username or len(username) < 2:
                errors.append("Username must be at least 2 characters long.")
                if any(char.isdigit() for char in username):
                    errors.append("Username cannot contain numbers.")
                if not email or '@' not in email:
                    errors.append("Please enter a valid email address.")
                if User.query.filter_by(email=email).first():
                    errors.append("Email is already registered.")
                if not password or len(password) < 6:
                    errors.append("Password must be at least 6 characters long.")
                if password != confirm_password:
                    errors.append("Passwords do not match.")

            if errors:
               return render_template('register.html', errors=errors, username=username, email=email)

            # Hash the password and save the new user to the database
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            new_user = User(username=username, email=email, password=hashed_password.decode('utf-8'), role='user')   
            db.session.add(new_user)
            db.session.commit()

            # Auto create a TalentProfile for the new user
            talent_profile = TalentProfile(user_id=new_user.id, username=username)
            db.session.add(talent_profile)
            db.session.commit()

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        return render_template('register.html', errors=[])
        
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            user = User.query.filter_by(email=email).first()

            if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
                login_user(user)
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error='Invalid email or password.')

        return render_template('login.html', error='')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/forgot_password', methods=['GET', 'POST'])
    def forgot_password():
        step = request.args.get('step', '1')
        error = None

        if request.method == 'POST':
            if step == '1':
                email = request.form.get('email','').strip().lower()
                user = User.query.filter_by(email=email).first()

                if user:
                    # Generate a secure token and store it with the user's ID
                    token = secrets.token_urlsafe(16)
                    reset_tokens[token] = email

                    print(f"reset token for {email}: {token}")
                    flash(f"Password Reset Token: {token}", "info")
                    return redirect(url_for('forgot_password', step='2', token=token))
                else:
                    error = "Email not found. Please check and try again."

            elif step == '2': 
                token = request.form.get('token', '').strip()
                new_password = request.form.get('new_password', '')
                confirm_password = request.form.get('confirm_password', '')

                if token not in reset_tokens:
                    error = "Invalid or expired token. Please request a new password reset."

                elif len(new_password) < 6:
                    error = "Password must be at least 6 characters long."
                elif new_password != confirm_password:
                    error = "Passwords do not match."
                else:
                    email = reset_tokens.pop(token)
                    user = User.query.filter_by(email=email).first()
                    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                    user.password = hashed_password.decode('utf-8')
                    db.session.commit()
                    flash("Password reset successful! Please log in with your new password.", "success")
                    return redirect(url_for('login'))
        return  render_template('forgot_password.html', step=step, error=error)

    #================================================================================================
    # DASHBOARD AND PROFILE ROUTES
    #================================================================================================

    @app.route('/dashboard')
    @login_required 
    def dashboard():
      profile = TalentProfile.query.filter_by(user_id=current_user.id).first()
      return render_template('dashboard.html', profile=profile)



    @app.route('/profile/edit', methods=['GET', 'POST'])
    @login_required
    def edit_profile():
        profile = TalentProfile.query.filter_by(user_id=current_user.id).first()
        if not profile:
           profile = TalentProfile(user_id=current_user.id, username=current_user.username)


        if request.method == 'POST':
            profile.username = request.form.get('username', profile.username).strip()
            profile.bio = request.form.get('bio', profile.bio).strip()
            profile.skills = request.form.get('skills', profile.skills).strip()
            profile.experience = request.form.get('experience', profile.experience).strip()
            profile.portfolio = request.form.get('portfolio', profile.portfolio).strip()
            db.session.add(profile)
            db.session.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for('dashboard'))

        return render_template('edit_profile.html', profile=profile)


    @app.route('/profile/upload_photo', methods=['POST'])
    @login_required 
    def upload_photo():
        file = request.files.get('photo')
        if not file or file.filename == '':
            flash("No file selected.", "error")
            return redirect(url_for('dashboards'))

        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in {'png', 'jpg', 'jpeg'}:
            flash("Invalid file type. Only PNG, JPG, and JPEG are allowed.", "error")
            return redirect(url_for('dashboard'))

        from werkzeug.utils import secure_filename
        filename = secure_filename(f"user_{current_user.id}.{ext}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        profile = TalentProfile.query.filter_by(user_id=current_user.id).first()
        if not profile:
            profile = TalentProfile(user_id=current_user.id, username=current_user.username)
        profile.photo = filename
        db.session.add(profile)
        db.session.commit()
        flash("Photo uploaded successfully!", "success")
        return redirect(url_for('dashboard'))

    @app.route('/profile/download_photo')
    @login_required
    def download_profile():
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4

        profile = TalentProfile.query.filter_by(user_id=current_user.id).first()
        tmp     = os.path.join(tempfile.gettempdir(), f"profile_{current_user.id}.pdf")
        c       = rl_canvas.Canvas(tmp, pagesize=A4)


        c.setFillColorRGB(0.06, 0.13, 0.40)
        c.rect(0, 750, 600, 92, fill=True, stroke=False)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(40,800, profile.name or 'Talent Profile')
        c.setFont("Helvetica", 12)
        c.drawString(40,775,'Perficient -- Talent Profile')

        c.setFillColoRGB(0, 0 ,0)
        c.setFont("Helvetica-Bold",13)
        c.drawString(40,720,'Skills:')
        c.setFont("Helvetica",11)
        c.drawString(40,700, profile.skills or 'N/A')

        c.setFont("Helvetica-Bold",13)
        c.drawString(40,670,'Bio:')
        c.setFont("Helvetica",11)
        c.drawString(40,650, profile.bio or 'N/A')

        c.setFont("Helvetica-Bold",13)
        c.drawString(40,620,'Experience:')
        c.setFont("Helvetica",11)           
        c.drawString(40,600, profile.experience or 'N/A')

        c.setFont("Helvetica-Bold",13)
        c.drawString(40,570,'Portfolio:')
        c.setFont("Helvetica",11)
        c.drawString(40,550, profile.portfolio or 'N/A')

        c.save()
        return send_file(tmp, as_attachment=True, download_name=f"{profile.name}_Peficient_Profile.pdf")


    #================================================================================================
    # BROWSWING AND SEARCH ROUTES
    #================================================================================================

    @app.route('/browse')
    def browse():
        search = request.args.get('q', '')
        page  = request.args.get('page', 1, type=int)
        query = TalentProfile.query.filter(TalentProfile.name != None)
        if search:
            query = query.filter(TalentProfile.name.ilike(f'%{search}%') |
                                 TalentProfile.skills.ilike(f'%{search}%'))

        profiles = query.paginate(page=page, per_page=9)
        return render_template('browse.html', profiles=profiles, search=search)


#================================================================================================
# REST API ROUTES/ENDPOINTS
#================================================================================================

@app.route('/api/talents', methods=['GET'])
def api_all_talents():
    profiles = TalentProfile.query.filter(TalentProfile.name != None).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'skills': p.skills,
        'bio': p.bio,
        'experience': p.experience,
        'portfolio': p.portfolio,
        'photo_url': url_for('static', filename=f'uploads/{p.photo}') if p.photo else None
    } for p in profiles]) 

@app.route('/api/talent/<int:id>', methods=['GET'])
def api_talent(id):
    p = TalentProfile.query.get_or_404(id)
    return jsonify({
        'id': p.id,
        'name': p.name,
        'skills': p.skills,
        'bio': p.bio,
        'experience': p.experience,
        'portfolio': p.portfolio,
        'photo_url': url_for('static', filename=f'uploads/{p.photo}') if p.photo else None
    })

#================================================================================================
# ADMIN ROUTES
#================================================================================================   

@app.route('/admin/profiles')
@login_required
@admin_required
def admin_profiles():
    profiles = TalentProfile.query.all()
    return render_template('admin_profiles.html', profiles=profiles)


if __name__ == '__main__':
    app.run(debug=True)