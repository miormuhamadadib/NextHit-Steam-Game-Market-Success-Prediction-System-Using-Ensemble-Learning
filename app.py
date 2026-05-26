from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import joblib
import pandas as pd
import mysql.connector

app = Flask(__name__)

# Required for using sessions
app.secret_key = 'mY_f1n4L_y3aR_pr0j3cT_k3y_9921'

@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response
# --------------------------

import os

# 1. Load the model and features
base_dir = os.path.dirname(os.path.abspath(__file__))

model_path = os.path.join(base_dir, 'model', 'final_steam_model_best.pkl')
features_path = os.path.join(base_dir, 'model', 'final_model_features_best.pkl')

model = joblib.load(model_path)
features = joblib.load(features_path)

# 2. Database Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Mior2581588_',  
    'database': 'game_predictions'
}

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

# --- SMART ADVISOR ENGINE ---
def generate_recommendations(input_df, prediction_text, top_influencers):
    recs = []
    
    # If the game isn't highly successful, find ways to improve it
    if 'High' not in prediction_text:
        # Check Localization
        if input_df['lang_count'].iloc[0] < 3:
            recs.append("Market Expansion: Consider localizing your game into more languages (e.g., Spanish, Simplified Chinese) to significantly increase your global market reach.")
            
        # Check Achievements
        if input_df['Achievements'].iloc[0] == 0:
            recs.append("Player Retention: Adding Steam Achievements is a low-cost feature that historically boosts player retention and algorithm visibility.")
            
        # Check Marketing
        if input_df['has_website'].iloc[0] == 0:
            recs.append("Marketing Hub: Build an official website or dedicated landing page to establish credibility and centralize your pre-launch marketing.")
            
        # Dynamic advice based on their specific top driver
        if len(top_influencers) > 0:
            top_feature = top_influencers[0]['name']
            recs.append(f"Core Focus: Your market potential is heavily influenced by the '{top_feature}' tag. Ensure this specific aspect of your game is highly polished before launch.")
            
    else:
        # If they already have High Success
        recs.append("Optimal Profile: Your current metadata profile is incredibly strong. Focus your remaining budget on community building and generating Steam Wishlists.")
        
    return recs

def get_similar_games(input_price, input_genres, input_tags, limit=3):
    df_full = pd.read_csv('steam_games_clean.csv')
    
    # Try a wider range if the first one is too small (+/- $10 instead of $5)
    price_mask = (df_full['Price'] >= input_price - 10) & (df_full['Price'] <= input_price + 10)
    potential_matches = df_full[price_mask].copy()

    # If STILL empty, just show top games in that genre regardless of price
    if potential_matches.empty:
        potential_matches = df_full.copy()

    def calculate_overlap(row_tags):
        tags_list = row_tags.split(', ') if isinstance(row_tags, str) else []
        overlap = set(tags_list) & set(input_genres + input_tags)
        return len(overlap)

    # Use the correct CSV column name here (all_tags, Genres, etc.)
    potential_matches['match_score'] = potential_matches['Tags'].apply(calculate_overlap)
    
    similar_games = potential_matches.sort_values(by=['match_score', 'Positive'], ascending=False).head(limit)
    return similar_games.to_dict('records')



# 3. Home Route
@app.route('/')
def home():
    # home() now only renders the blank page. 
    # Results are only shown when /predict returns them directly.
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
        # --- 1. Collect Inputs ---
        price = float(request.form.get('price', 0))
        languages = int(request.form.get('languages', 1))
        platforms = int(request.form.get('platforms', 1))
        achievements = int(request.form.get('achievements', 0))
        dlc = int(request.form.get('dlc', 0))
        devs = int(request.form.get('devs', 1))
        website = 1 if request.form.get('website') == 'on' else 0
        month = int(request.form.get('month', 1))
        
        genres_input = request.form.getlist('genres')
        tags_input = request.form.getlist('tags')
        genres_raw = ", ".join(genres_input)
        tags_raw = ", ".join(tags_input)

        # --- 2. Find Similar Games locally (Don't put in session!) ---
        similar_games = get_similar_games(price, genres_input, tags_input)
        
        # --- 3. Run Prediction Logic ---
        input_df = pd.DataFrame(0, index=[0], columns=features)
        input_df['Price'] = price
        input_df['lang_count'] = languages
        input_df['platform_count'] = platforms
        input_df['Achievements'] = achievements
        input_df['DLC count'] = dlc
        input_df['dev_count'] = devs
        input_df['has_website'] = website
        input_df['release_month'] = month

        for item in (genres_input + tags_input):
            if item in input_df.columns:
                input_df[item] = 1
        
        prediction_idx = model.predict(input_df)[0]
        probabilities = model.predict_proba(input_df)[0]
        confidence_score = float(round(probabilities[prediction_idx] * 100, 2))
        
        success_map = {0: 'Low Success', 1: 'Moderate Success', 2: 'High Success'}
        result = success_map[prediction_idx]

        # --- 4. Importance & Recommendations ---
        active_features = [col for col in input_df.columns if input_df.iloc[0][col] > 0]
        importance_map = dict(zip(features, model.feature_importances_))
        top_influencers = sorted(
            [{'name': f, 'weight': float(importance_map.get(f, 0))} for f in active_features],
            key=lambda x: x['weight'], reverse=True
        )[:3]
        
        drivers_str = ", ".join([d['name'] for d in top_influencers])
        recommendations = generate_recommendations(input_df, result, top_influencers)

        # --- 5. Save to DB ---
        user_id = session.get('id')
        save_to_db(user_id, price, genres_raw, tags_raw, result, drivers_str)
        
        # --- 6. RENDER DIRECTLY (The Critical Fix) ---
        # We pass the variables directly. This bypasses the cookie size limit.
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
    # Explicitly remove the exact keys causing the results to show
    session.pop('prediction_text', None)
    session.pop('original_input', None)
    session.pop('top_influencers', None)
    session.pop('confidence', None)
    session.pop('similar_games', None)
    
    # Force Flask to update the cookie in the user's browser
    session.modified = True 
    
    return redirect(url_for('home'))

@app.route('/history')
def history():

    # Inside your /history route (after the security check)
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Notice there is NO 'WHERE' clause. This pulls the entire database table.
    cursor.execute("SELECT * FROM predictions ORDER BY created_at DESC")
    rows = cursor.fetchall()

    # --- SECURITY CHECK ---
    if session.get('role') != 'admin':
        flash('Access Denied: Administrator privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    # ----------------------

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM predictions ORDER BY created_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('history.html', rows=rows)
    except Exception as e:
        return f"Database Error: {e}"

@app.route('/clear_history', methods=['POST'])
def clear_history():

    # --- SECURITY CHECK ---
    if session.get('role') != 'admin':
        flash('Access Denied: Administrator privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    # ----------------------

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM predictions")
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('history'))
    except Exception as e:
        return f"Database Error: {e}"
    


# --- BOOKMARKING ROUTE ---
@app.route('/toggle_bookmark/<int:record_id>', methods=['POST'])
def toggle_bookmark(record_id):
    # Security: Ensure user is logged in
    if 'loggedin' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch the current bookmark status for this specific prediction
        cursor.execute("SELECT is_bookmarked FROM predictions WHERE id = %s", (record_id,))
        record = cursor.fetchone()
        
        if not record:
            return jsonify({'success': False, 'message': 'Record not found'}), 404

        # 2. Toggle the boolean value (If 0 make it 1, if 1 make it 0)
        new_status = not record['is_bookmarked']
        
        # 3. Update the database with the new status
        cursor.execute("UPDATE predictions SET is_bookmarked = %s WHERE id = %s", (new_status, record_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # 4. Return success to the frontend
        return jsonify({'success': True, 'is_bookmarked': new_status})
        
    except Exception as e:
        print(f"Bookmark Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/dashboard')
def dashboard():
    # 1. Security Check: Kick them out if they aren't logged in
    if 'loggedin' not in session:
        flash('Please log in to access your dashboard.', 'danger')
        return redirect(url_for('login'))
        
    user_id = session['id']
    username = session['username']
    
    # 2. Fetch the user's prediction history
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Assuming your predictions table has a 'created_at' and 'prediction' column
    cursor.execute("SELECT * FROM predictions WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    history = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # 3. Calculate Quick Stats for the UI
    total_runs = len(history)
    # Adjust 'prediction' below to match the exact column name in your database where the result is saved!
    high_success = sum(1 for p in history if p.get('prediction_result') == 'High Success') 
    
    return render_template('dashboard.html', 
                           username=username, 
                           history=history, 
                           total_runs=total_runs, 
                           high_success=high_success)


# --- USER AUTHENTICATION ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Hash the password for security
        hashed_password = generate_password_hash(password)
        
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Username already exists. Please choose another.', 'danger')
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
        
        # Check if user exists and password matches the hash
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


if __name__ == '__main__':
    app.run(debug=True)