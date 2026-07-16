from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import joblib
import pandas as pd
import numpy as np
import mysql.connector
import os
from datetime import datetime
import csv
from io import StringIO
# --- Forgot Password Routes ---
import secrets
import re
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests  # For SendGrid API

app = Flask(__name__)

# Required for using sessions
app.secret_key = os.environ.get('SECRET_KEY', 'a_default_dev_key_if_missing')

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# --------------------------
# 1. LOAD THE NEW AI ARTIFACTS
# --------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))

# Set safe defaults
model = None
features = []
genre_mapping = {}
tags_mapping = {}

def get_file_path(filename):
    path_in_model = os.path.join(base_dir, 'model', filename)
    path_in_root = os.path.join(base_dir, filename)
    if os.path.exists(path_in_model): return path_in_model
    if os.path.exists(path_in_root): return path_in_root
    return path_in_model # Fallback

model_path = get_file_path('final_steam_model_tuned.pkl')
features_path = get_file_path('final_model_features_optimized.pkl')
mappings_path = get_file_path('target_encoding_mappings.pkl')

try:
    model = joblib.load(model_path)
    model.set_params(device='cpu') 
    features = joblib.load(features_path)
    mappings = joblib.load(mappings_path)
    
    genre_mapping = mappings.get('genres', {})
    tags_mapping = mappings.get('tags', {})
    
    # Strict verification
    if len(features) == 0:
        raise ValueError("Features file loaded successfully, but it was empty!")
        
    print("✅ NextHit AI Engine Loaded Successfully!")
except Exception as e:
    # THE FIX: If ANYTHING fails, reset the model to None so the server safely blocks predictions
    model = None 
    features = []
    print("\n" + "="*50)
    print(f"❌ CRITICAL ERROR: Could not load AI files!")
    print(f"Error Details: {e}")
    print("Please ensure your three .pkl files are properly placed.")
    print("="*50 + "\n")

# 2. Database Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': os.environ.get('DB_PASSWORD'),  
    'database': 'game_predictions'
}

# 3. SendGrid Email Configuration
# Get your SendGrid API Key from: https://app.sendgrid.com/settings/api_keys
# Free tier: 100 emails/day
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
SENDGRID_FROM_EMAIL = os.environ.get('SENDGRID_FROM_EMAIL')

def send_reset_email(user_email, username, reset_link):
    """Send password reset email using SendGrid API"""
    try:
        # SendGrid API endpoint
        url = "https://api.sendgrid.com/v3/mail/send"
        
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Email content
        data = {
            "personalizations": [
                {
                    "to": [{"email": user_email}],
                    "subject": "Reset Your NextHit Password"
                }
            ],
            "from": {"email": SENDGRID_FROM_EMAIL},
            "content": [
                {
                    "type": "text/html",
                    "value": f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <style>
                            body {{ font-family: Arial, sans-serif; background-color: #121212; color: #e0e0e0; }}
                            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background-color: #1e1e1e; border-radius: 10px; }}
                            .header {{ text-align: center; padding: 20px 0; border-bottom: 1px solid #333; }}
                            .logo {{ color: #00ff88; font-size: 28px; font-weight: bold; }}
                            .content {{ padding: 30px 0; }}
                            .button {{
                                display: inline-block;
                                padding: 12px 30px;
                                background-color: #00ff88;
                                color: #121212;
                                text-decoration: none;
                                border-radius: 6px;
                                font-weight: bold;
                            }}
                            .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #333; font-size: 12px; color: #888; }}
                            .warning {{ color: #ff4b2b; font-size: 12px; margin-top: 15px; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="header">
                                <div class="logo">✦ NextHit</div>
                                <p style="color: #888; margin: 5px 0;">Predictive Market Intelligence</p>
                            </div>
                            <div class="content">
                                <h2 style="color: #fff;">Hi {username},</h2>
                                <p>We received a request to reset your password for your NextHit account.</p>
                                <p>Click the button below to create a new password:</p>
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{reset_link}" class="button">Reset Password</a>
                                </div>
                                <p style="color: #888;">This link will expire in <strong style="color: #fff;">1 hour</strong>.</p>
                                <p class="warning">If you didn't request this, please ignore this email. Your password will remain unchanged.</p>
                            </div>
                            <div class="footer">
                                <p>© 2024 NextHit. All rights reserved.</p>
                                <p>This is an automated message, please do not reply.</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                }
            ]
        }
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 202:
            print(f"✅ Reset email sent to {user_email}")
            return True
        else:
            print(f"❌ SendGrid error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Email sending error: {e}")
        return False

def save_to_db(user_id, price, genres, tags, result, drivers_str):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = "INSERT INTO predictions (user_id, price, genres, tags, prediction_result, top_drivers) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(query, (user_id, price, genres, tags, result, drivers_str))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")

# --- SMART ADVISOR ENGINE V2 ---
def generate_recommendations(input_df, prediction_text, top_influencers):
    recs = []
    
    # --- 1. Top Driver Advice ---
    if top_influencers: # Simplified check for non-empty list
        top_driver = top_influencers[0]['name']
        
        # This structure is more maintainable and avoids repeating the intro sentence.
        advice_snippets = {
            'Multiplayer': "Multiplayer games live or die by server stability. Prioritize a closed beta to stress-test your netcode before launch.",
            'Singleplayer': "Singleplayer success relies heavily on pacing and replayability. Consider adding a 'New Game+' mode or branching narratives.",
            'Story Rich': "Ensure your script is heavily proofread and localized. Poor translations can severely hurt Story Rich game reviews.",
            'Early Access': "Early Access requires community trust. Publish a clear 6-month roadmap on your Steam page immediately.",
            'RPG': "RPG players expect deep progression systems. Ensure your skill trees are clearly showcased in your gameplay trailer.",
            'Action': "The Action market is highly visual. Invest heavily in high-framerate gameplay GIFs for your Steam store page.",
            'FPS': "FPS players are highly sensitive to gunplay mechanics. Ensure your sound design and hit-markers feel incredibly punchy.",
            'Horror': "Atmosphere is everything in Horror. Rely on lighting and audio design rather than cheap jump scares to build tension.",
            'Open World': "Avoid 'empty map' syndrome. Ensure there are meaningful encounters or dynamic events between major landmarks.",
            'Simulation': "Simulation fans value realism and depth. Highlight the complexity of your physics or management systems in your marketing."
        }
        
        # Get the specific advice snippet, or use a generic fallback.
        advice_body = advice_snippets.get(
            top_driver, 
            "Ensure your marketing materials explicitly highlight this aspect of your game."
        )
        
        # Combine the intro with the specific advice body.
        full_advice = f"Your market potential is heavily anchored by the #{top_driver} feature. {advice_body}"
        recs.append(full_advice)

    # --- 2. General Improvement Advice (for non-High predictions) ---
    if 'High' not in prediction_text:
        # Check if the number of languages is low.
        if 'lang_count' in input_df.columns and input_df['lang_count'].iloc[0] < 3:
            recs.append("Localization Gap: You are supporting fewer than 3 languages. Translating your UI/Subtitles into Spanish or Simplified Chinese historically boosts sales by up to 30%.")
        # Check if a website is missing.
        if 'has_website' in input_df.columns and input_df['has_website'].iloc[0] == 0:
            recs.append("Missing Hub: Games without official websites often struggle to build pre-launch mailing lists. Set up a simple landing page to capture emails.")

    return recs

def get_similar_games(input_price, input_genres, input_tags, limit=3):
    try:
        csv_path = os.path.join(base_dir, 'steam_games_clean.csv')
        df_full = pd.read_csv(csv_path)
        
        def has_matching_genre(row_genres):
            if not isinstance(row_genres, str): return False
            game_genres = set(row_genres.split(', '))
            user_genres = set(input_genres)
            return len(game_genres.intersection(user_genres)) > 0

        if len(input_genres) > 0 and 'Genres' in df_full.columns:
            genre_mask = df_full['Genres'].apply(has_matching_genre)
            genre_matches = df_full[genre_mask].copy()
            if genre_matches.empty:
                genre_matches = df_full.copy()
        else:
            genre_matches = df_full.copy()

        price_mask = (genre_matches['Price'] >= input_price - 10) & (genre_matches['Price'] <= input_price + 10)
        potential_matches = genre_matches[price_mask].copy()

        if potential_matches.empty:
            potential_matches = genre_matches.copy()

        def calculate_overlap(row_tags):
            tags_list = row_tags.split(', ') if isinstance(row_tags, str) else []
            overlap = set(tags_list) & set(input_genres + input_tags)
            return len(overlap)

        potential_matches['match_score'] = potential_matches['Tags'].apply(calculate_overlap)
        similar_games = potential_matches.sort_values(by=['match_score', 'Positive'], ascending=False).head(limit)
        return similar_games.to_dict('records')
    except Exception as e:
        print(f"Error fetching similar games: {e}")
        return []

# 3. Home Route
@app.route('/')
def home():
    return render_template('index.html', 
                           prediction_text=None,
                           confidence=None, 
                           original_input=None,
                           top_influencers=[],
                           recommendations=[],
                           similar_games=[])

# 4. Prediction Route
@app.route('/predict', methods=['POST'])
def predict():
    if request.method == 'POST':
        # THE FIX: Prevent silent crashes. This guarantees we don't feed 0 columns to the AI.
        if model is None or len(features) == 0:
            return "<h1>Server Error</h1><p>The AI Model or Feature list failed to load during server startup. Please check your Python terminal logs to see which .pkl file is missing or corrupted.</p>", 500

        try:
            price = float(request.form.get('price') or 0.0)
            languages = int(request.form.get('languages') or 1)
            platforms = int(request.form.get('platforms') or 1)
            achievements = int(request.form.get('achievements') or 0)
            dlc = int(request.form.get('dlc') or 0)
            devs = int(request.form.get('devs') or 1)
            month = int(request.form.get('month') or 1)
        except ValueError:
            price, languages, platforms, achievements, dlc, devs, month = 0.0, 1, 1, 0, 0, 1, 1

        website = 1 if request.form.get('website') == 'on' else 0
        
        genres_input = [g.strip() for g in request.form.getlist('genres') if g.strip()]
        tags_input = [t.strip() for t in request.form.getlist('tags') if t.strip()]
        genres_raw = ", ".join(genres_input)
        tags_raw = ", ".join(tags_input)

        similar_games = get_similar_games(price, genres_input, tags_input)
        
        def get_encoded_weight(items_list, mapping_dict):
            if not items_list: return 0.0
            weights = [mapping_dict.get(item, 0.0) for item in items_list]
            return float(np.mean(weights)) if weights else 0.0

        genre_w = get_encoded_weight(genres_input, genre_mapping)
        tag_w = get_encoded_weight(tags_input, tags_mapping)

        # BUILD THE 50-COLUMN DATAFRAME
        input_df = pd.DataFrame(0.0, index=[0], columns=features)
        
        safe_inject = {
            'Price': price,
            'dev_count': float(devs),
            'has_website': float(website),
            'lang_count': float(languages),
            'release_month': float(month),
            'platform_count': float(platforms),
            'genre_weight': genre_w,
            'tags_weight': tag_w
        }
        for col, val in safe_inject.items():
            if col in input_df.columns:
                input_df.at[0, col] = val

        for item in (genres_input + tags_input):
            if item in input_df.columns:
                input_df.at[0, item] = 1.0
        
        # MAKE THE PREDICTION
        prediction_idx = int(model.predict(input_df.values)[0])
        probabilities = model.predict_proba(input_df.values)[0]
        confidence_score = float(round(max(probabilities) * 100, 2))
        
        success_map = {0: 'Low Success', 1: 'Moderate Success', 2: 'High Success'}
        result = success_map[prediction_idx]

        active_features = [col for col in input_df.columns if input_df.at[0, col] > 0]
        importance_map = dict(zip(features, model.feature_importances_))
        top_influencers = sorted(
            [{'name': f, 'weight': float(importance_map.get(f, 0))} for f in active_features],
            key=lambda x: x['weight'], reverse=True
        )[:3]
        
        drivers_str = ", ".join([d['name'] for d in top_influencers])
        recommendations = generate_recommendations(input_df, result, top_influencers)

        user_id = session.get('id')
        save_to_db(user_id, price, genres_raw, tags_raw, result, drivers_str)
        
        return render_template('index.html', 
                               prediction_text=result,
                               confidence=confidence_score, 
                               top_influencers=top_influencers,
                               recommendations=recommendations,
                               similar_games=similar_games,
                               original_input={
                                   'price': price, 'genres': genres_raw, 'tags': tags_raw,
                                   'month': month, 'languages': languages, 'platforms': platforms,
                                   'devs': devs, 'achievements': achievements, 'dlc': dlc, 
                                   'website': request.form.get('website')
                               })

@app.route('/reset')
def reset():
    session.pop('prediction_text', None)
    session.pop('original_input', None)
    session.pop('top_influencers', None)
    session.pop('confidence', None)
    session.pop('similar_games', None)
    session.modified = True 
    return redirect(url_for('home'))

@app.route('/history')
def history():
    if session.get('role') != 'admin':
        flash('Access Denied: Administrator privileges required.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT p.*, u.username FROM predictions p LEFT JOIN users u ON p.user_id = u.id ORDER BY p.created_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('history.html', rows=rows)
    except Exception as e:
        return f"Database Error: {e}"

@app.route('/clear_history', methods=['POST'])
def clear_history():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM predictions")
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'History cleared successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/toggle_bookmark/<int:record_id>', methods=['POST'])
def toggle_bookmark(record_id):
    if 'loggedin' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT is_bookmarked FROM predictions WHERE id = %s", (record_id,))
        record = cursor.fetchone()
        
        if not record:
            return jsonify({'success': False, 'message': 'Record not found'}), 404

        new_status = not record['is_bookmarked']
        
        cursor.execute("UPDATE predictions SET is_bookmarked = %s WHERE id = %s", (new_status, record_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'is_bookmarked': new_status})
        
    except Exception as e:
        print(f"Bookmark Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/dashboard')
def dashboard():
    if 'loggedin' not in session:
        flash('Please log in to access your dashboard.', 'danger')
        return redirect(url_for('login'))
        
    user_id = session['id']
    username = session['username']
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM predictions WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    history = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    total_runs = len(history)
    high_success = sum(1 for p in history if p.get('prediction_result') == 'High Success') 
    
    return render_template('dashboard.html', 
                           username=username, 
                           history=history, 
                           total_runs=total_runs, 
                           high_success=high_success)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form.get('email', '').strip()
        password = request.form['password']
        
        # Validate email
        if not email:
            flash('Email address is required.', 'danger')
            return render_template('register.html')
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        try:
            cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", 
                          (username, email, hashed_password))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError as e:
            if 'username' in str(e):
                flash('Username already exists. Please choose another.', 'danger')
            elif 'email' in str(e):
                flash('Email already registered. Please use another email or login.', 'danger')
            else:
                flash('Registration failed. Please try again.', 'danger')
        finally:
            cursor.close()
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['loggedin'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role'] 
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect username or password!', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear() 
    return redirect(url_for('home'))

# ============================================
# FORGOT PASSWORD ROUTES
# ============================================

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('forgot_password.html')
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('forgot_password.html')
        
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Check if user exists with this email
        cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            # Don't reveal if email exists or not (security)
            flash('If an account with that email exists, we\'ve sent a password reset link.', 'success')
            return render_template('forgot_password.html')
        
        # Generate reset token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=1)
        
        # Store token in database
        cursor.execute("""
            INSERT INTO password_reset_tokens (user_id, token, expires_at)
            VALUES (%s, %s, %s)
        """, (user['id'], token, expires_at))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # Send reset email using SendGrid
        reset_link = url_for('reset_password', token=token, _external=True)
        email_sent = send_reset_email(email, user['username'], reset_link)
        
        if email_sent:
            flash('Password reset link has been sent to your email.', 'success')
        else:
            flash('Failed to send reset email. Please try again later.', 'danger')
        
        return render_template('forgot_password.html')
    
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Validate token
    cursor.execute("""
        SELECT user_id, expires_at, used 
        FROM password_reset_tokens 
        WHERE token = %s
    """, (token,))
    token_data = cursor.fetchone()
    
    if not token_data:
        flash('Invalid or expired password reset link.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('login'))
    
    # Check if token is expired or used
    if token_data['used']:
        flash('This password reset link has already been used.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('login'))
    
    if datetime.now() > token_data['expires_at']:
        flash('This password reset link has expired. Please request a new one.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate password
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            cursor.close()
            conn.close()
            return render_template('reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            cursor.close()
            conn.close()
            return render_template('reset_password.html', token=token)
        
        # Update password
        hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", 
                      (hashed_password, token_data['user_id']))
        
        # Mark token as used
        cursor.execute("UPDATE password_reset_tokens SET used = TRUE WHERE token = %s", (token,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash('Your password has been reset successfully! Please log in with your new password.', 'success')
        return redirect(url_for('login'))
    
    cursor.close()
    conn.close()
    
    return render_template('reset_password.html', token=token)

# ============================================
# ADMIN ROUTES
# ============================================

@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Access Denied: Administrator privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Total predictions
    cursor.execute("SELECT COUNT(*) as total FROM predictions")
    total_predictions = cursor.fetchone()['total']
    
    # Total users
    cursor.execute("SELECT COUNT(*) as total FROM users")
    total_users = cursor.fetchone()['total']
    
    # High success count
    cursor.execute("SELECT COUNT(*) as count FROM predictions WHERE prediction_result = 'High Success'")
    high_success_count = cursor.fetchone()['count']
    
    # Today's predictions
    cursor.execute("SELECT COUNT(*) as count FROM predictions WHERE DATE(created_at) = CURDATE()")
    today_predictions = cursor.fetchone()['count']
    
    # Distribution
    cursor.execute("""
        SELECT prediction_result, COUNT(*) as count 
        FROM predictions 
        GROUP BY prediction_result
    """)
    distribution = cursor.fetchall()
    
    # Daily activity (last 7 days)
    cursor.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count 
        FROM predictions 
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) 
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    daily_activity = cursor.fetchall()
    
    # Top genres
    cursor.execute("""
        SELECT genres, COUNT(*) as count 
        FROM predictions 
        WHERE genres != '' 
        GROUP BY genres 
        ORDER BY COUNT(*) DESC 
        LIMIT 10
    """)
    top_genres = cursor.fetchall()
    
    # User activity
    cursor.execute("""
        SELECT 
            u.id,
            u.username,
            u.role,
            COUNT(p.id) as prediction_count,
            (
                SELECT prediction_result 
                FROM predictions 
                WHERE user_id = u.id 
                GROUP BY prediction_result 
                ORDER BY COUNT(*) DESC 
                LIMIT 1
            ) as most_common_result
        FROM users u 
        LEFT JOIN predictions p ON u.id = p.user_id 
        GROUP BY u.id 
        ORDER BY prediction_count DESC 
        LIMIT 10
    """)
    user_activity = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # Get last updated time
    last_updated = datetime.now().strftime('%H:%M:%S')
    
    return render_template('admin_dashboard.html',
                         total_predictions=total_predictions,
                         total_users=total_users,
                         high_success_count=high_success_count,
                         today_predictions=today_predictions,
                         distribution=distribution,
                         daily_activity=daily_activity,
                         top_genres=top_genres,
                         user_activity=user_activity,
                         last_updated=last_updated)

@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        flash('Access Denied', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT u.*, COUNT(p.id) as prediction_count 
        FROM users u 
        LEFT JOIN predictions p ON u.id = p.user_id 
        GROUP BY u.id 
        ORDER BY u.created_at DESC
    """)
    users = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>/toggle_role', methods=['POST'])
def toggle_user_role(user_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        new_role = 'user' if user['role'] == 'admin' else 'admin'
        cursor.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'new_role': new_role})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    if user_id == session.get('id'):
        return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Delete user's predictions first (foreign key constraint)
        cursor.execute("DELETE FROM predictions WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/user/<int:user_id>')
def view_user(user_id):
    if session.get('role') != 'admin':
        flash('Access Denied', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('admin_users'))
    
    cursor.execute("SELECT * FROM predictions WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    predictions = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('view_user.html', user=user, predictions=predictions)

@app.route('/admin/model_performance')
def model_performance():
    if session.get('role') != 'admin':
        flash('Access Denied', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Get prediction distribution with counts
    cursor.execute("""
        SELECT 
            prediction_result,
            COUNT(*) as count,
            ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM predictions), 2) as percentage
        FROM predictions
        GROUP BY prediction_result
    """)
    distribution = cursor.fetchall()
    
    # Get monthly trends
    cursor.execute("""
        SELECT 
            DATE_FORMAT(created_at, '%Y-%m') as month,
            COUNT(*) as total,
            SUM(CASE WHEN prediction_result = 'High Success' THEN 1 ELSE 0 END) as high_success
        FROM predictions
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month
    """)
    monthly_trends = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('model_performance.html',
                         distribution=distribution,
                         monthly_trends=monthly_trends)

@app.route('/admin/feature_importance')
def feature_importance():
    if session.get('role') != 'admin':
        flash('Access Denied', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get feature importance from your model
    if model is not None and hasattr(model, 'feature_importances_'):
        # Convert numpy.float32 to Python float
        importance_dict = dict(zip(features, model.feature_importances_))
        # Convert all values to Python float
        importance_dict = {k: float(v) for k, v in importance_dict.items()}
        sorted_importance = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)[:20]
        return render_template('feature_importance.html', features=sorted_importance)
    else:
        flash('Feature importance not available', 'warning')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/system_health')
def system_health():
    if session.get('role') != 'admin':
        flash('Access Denied', 'danger')
        return redirect(url_for('dashboard'))
    
    health_data = {
        'database_status': 'Connected',
        'model_status': 'Loaded' if model is not None else 'Error',
        'total_predictions': 0,
        'unique_users': 0,
        'last_24h_predictions': 0,
        'server_uptime': 'Unknown',
        'memory_usage': 'Unknown'
    }
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT COUNT(*) as total FROM predictions")
        health_data['total_predictions'] = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM predictions")
        health_data['unique_users'] = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM predictions 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """)
        health_data['last_24h_predictions'] = cursor.fetchone()['count']
        
        # Check if we can connect to the database
        health_data['database_status'] = 'Connected'
        
        cursor.close()
        conn.close()
    except Exception as e:
        health_data['database_status'] = f'Error: {str(e)}'
    
    # Get server uptime (Unix style - from when the server started)
    try:
        import psutil
        import time
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        health_data['server_uptime'] = f"{days}d {hours}h {minutes}m"
    except:
        health_data['server_uptime'] = 'N/A'
    
    return render_template('system_health.html', health_data=health_data)

@app.route('/admin/export_data')
def export_data():
    if session.get('role') != 'admin':
        flash('Access Denied', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Export all predictions with user info
        cursor.execute("""
            SELECT 
                p.id,
                p.price,
                p.genres,
                p.tags,
                p.prediction_result,
                p.top_drivers,
                p.created_at,
                u.username,
                u.role
            FROM predictions p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.created_at DESC
        """)
        data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Create CSV
        df = pd.DataFrame(data)
        
        # Format datetime columns
        if 'created_at' in df.columns:
            df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        
        response = make_response(csv_buffer.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=predictions_export.csv"
        response.headers["Content-type"] = "text/csv"
        
        return response
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/clear_all_predictions', methods=['POST'])
def clear_all_predictions():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM predictions")
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'All predictions cleared successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)