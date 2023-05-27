from flask import Flask, render_template, redirect, request, jsonify, session, flash
import mysql.connector
import requests
from mysql.connector import Error
import os
import bcrypt
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)



api_access_key = os.getenv('API_ACCESS_KEY')
mysql_host = os.getenv('MYSQL_HOST')
mysql_database = os.getenv('MYSQL_DATABASE')
mysql_user = os.getenv('MYSQL_USER')
mysql_password = os.getenv('MYSQL_PASSWORD')
admin_username = os.getenv('ADMIN_USERNAME')
admin_password = os.getenv('ADMIN_PASSWORD')


# Check database connection
def check_database_connection():
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            user=mysql_user,
            password=mysql_password
        )
        conn.close()
        return True, "Database connection successful"
    except Error as e:
        error_message = f"Database connection error: {e}"
        return False, error_message


# Register the check_database_connection filter
app.jinja_env.filters['check_database_connection'] = check_database_connection


# Dashboard Page (Default Page)
@app.route('/')
def dashboard():
    connected, message = check_database_connection()
    database_status = f"Database Connection: {'Connected' if connected else 'Not Connected'}"

    description = "Welcome to the Dashboard! This is the main page of your application."
    additional_description = "Here, you can perform various actions and access different features."
    action_description = "To get started, you can log in or sign up using the links above."

    success_message = request.args.get('success')

    return render_template('dashboard.html', database_status=database_status, description=description,
                           additional_description=additional_description, action_description=action_description,
                           success_message=success_message)


# Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if is_valid_user(username, password):
            session['username'] = username
            if username == admin_username:
                # User is the admin, set the session variable
                session['admin_logged_in'] = True
                # Redirect to the admin page
                return redirect('/admin')
            else:
                # User is a client, redirect to the convert page
                return redirect('/convert')

        else:
            error_message = 'Invalid username or password.'
            return render_template('login.html', error=error_message)

    return render_template('login.html')


# Admin Page (requires login)
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    # Check if the user is logged in as admin
    if not is_admin_logged_in():
        # User is not logged in as admin, redirect to the login page
        return redirect('/login')

    if request.method == 'POST':
        # User clicked the logout button, clear the session
        session.clear()
        # Redirect to the login page
        return redirect('/login')

    # Retrieve all the data from the 'conversions' table
    conversions = get_all_conversions()

    success_message = session.pop('success_message', None)
    if success_message:
        flash(success_message)

    # Check if an error message exists in the session
    error_message = session.pop('error_message', None)
    if error_message:
        flash(error_message)

    if not conversions:
        flash('No data available to delete!', 'error')

    return render_template('admin.html', conversions=conversions)

# Check if the user is logged in as admin
def is_admin_logged_in():
    if 'username' in session:
        username = session['username']
        return username == admin_username
    return False

# Check if the user exists and the password is correct
def is_valid_user(username, password):
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            user=mysql_user,
            password=mysql_password
        )
        cursor = conn.cursor()

        select_query = "SELECT * FROM users WHERE username = %s"
        cursor.execute(select_query, (username,))
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if row is not None:
            hashed_password = row[2]
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

        return False

    except Error as e:
        print(f"Error validating user: {e}")
        return False

# Sign Up Page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error_message = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if is_username_taken(username):
            error_message = 'Username already taken. Please choose a different username.'
            return render_template('signup.html', error=error_message)
        else:
            save_user(username, password)
            session['username'] = username
            return redirect('/convert')

    return render_template('signup.html', error=error_message)


# Check if the username is already taken
def is_username_taken(username):
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            user=mysql_user,
            password=mysql_password
        )
        cursor = conn.cursor()

        select_query = "SELECT * FROM users WHERE username = %s"
        cursor.execute(select_query, (username,))
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        return row is not None

    except Error as e:
        print(f"Error checking username: {e}")
        return False


# Save the user to the database
def save_user(username, password):
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            user=mysql_user,
            password=mysql_password
        )
        cursor = conn.cursor()

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        insert_query = "INSERT INTO users (username, password) VALUES (%s, %s)"
        cursor.execute(insert_query, (username, hashed_password))
        conn.commit()

        cursor.close()
        conn.close()

    except Error as e:
        print(f"Error saving user: {e}")


# Convert Page
@app.route('/convert', methods=['GET', 'POST'])
def convert():
    if 'username' not in session:
        return redirect('/login')

    if request.method == 'POST':
        current_user = session['username']

        # Check if the user clicked the logout button
        if 'logout' in request.form:
            session.pop('username', None)
            return redirect('/login')

        # Get user input for target currency, source currency, and amount
        to_currency = request.form.get('to')
        from_currency = request.form.get('from')
        amount = float(request.form['amount'])

        # Make API request to perform the currency conversion
        url = f"https://api.apilayer.com/currency_data/convert?to={to_currency}&from={from_currency}&amount={amount}"
        headers = {
            "apikey": api_access_key
        }

        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            print("API URL:", url)
            print("API Response:", data)

            # Extract the converted amount from the API response
            converted_amount = data.get('result')

            # Get the currency sign for the selected currencies
            to_currency_sign = get_currency_sign(to_currency)
            from_currency_sign = get_currency_sign(from_currency)

            if converted_amount is not None:
                # Format the converted amount to two decimal places
                converted_amount = round(converted_amount, 2)
                # Save the conversion result to the database
                save_conversion(current_user, to_currency, from_currency, amount, converted_amount)
                
                # Render the result template with the converted amount and currency signs
                return render_template('result.html', amount=amount, from_currency=from_currency,
                           from_currency_sign=from_currency_sign, to_currency=to_currency,
                           to_currency_sign=to_currency_sign, converted_amount=converted_amount)
            else:
                # Conversion failed, show an error message
                error_message = 'Currency conversion failed. Please try again.'
                return render_template('converter.html', error=error_message)

        except requests.exceptions.RequestException as e:
            # Handle API request error
            error_message = f"An error occurred during the currency conversion: {str(e)}"
            return render_template('converter.html', error=error_message)
    return render_template('converter.html', username=session['username'])

def get_currency_sign(currency_code):
    
    currency_signs = {
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'JPY': '¥',
        'PHP': '₱'
    }

    return currency_signs.get(currency_code, '')  # Return an empty string if sign not found

# Save conversion result to the database
def save_conversion(username, to_currency, from_currency, amount, converted_amount):
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            user=mysql_user,
            password=mysql_password
        )
        cursor = conn.cursor()

        # Get the currency sign for the selected currencies
        to_currency_sign = get_currency_sign(to_currency)
        from_currency_sign = get_currency_sign(from_currency)

        # Prepare the SQL query to insert the conversion result
        query = "INSERT INTO conversions (username, to_currency, from_currency, amount, converted_amount) " \
                "VALUES (%s, %s, %s, %s, %s)"
        values = (username, to_currency, from_currency, amount, f"{to_currency_sign}{converted_amount:.2f}")

        # Execute the query
        cursor.execute(query, values)
        conn.commit()

        # Close the cursor and connection
        cursor.close()
        conn.close()

    except Error as e:
        print(f"Error saving conversion to the database: {e}")

def get_all_conversions():
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            user=mysql_user,
            password=mysql_password
        )
        cursor = conn.cursor()

        select_query = "SELECT * FROM conversions"
        cursor.execute(select_query)

        conversions = []
        for row in cursor.fetchall():
            conversion = {
                'id': row[0],
                'username': row[1],
                'from_currency': row[2],
                'to_currency': row[3],
                'amount': row[4],
                'converted_amount': row[5]
            }
            conversions.append(conversion)

        cursor.close()
        conn.close()

        return conversions

    except Error as e:
        print(f"Error retrieving conversions: {e}")
        return []


@app.route('/delete-all-data', methods=['GET', 'POST', 'DELETE'])
def delete_all_data():
    if request.method == 'POST':
        # Check if the user is logged in as admin
        if not is_admin_logged_in():
            # User is not logged in as admin, redirect to the login page
            return redirect('/login')

        # Delete all data from the 'conversions' table
        delete_query = "DELETE FROM conversions"
        reset_query = "ALTER TABLE conversions AUTO_INCREMENT = 1"
        try:
            conn = mysql.connector.connect(
                host=mysql_host,
                database=mysql_database,
                user=mysql_user,
                password=mysql_password
            )
            cursor = conn.cursor()
            cursor.execute(delete_query)
            cursor.execute(reset_query)
            conn.commit()

            cursor.close()
            conn.close()

            flash('All data deleted successfully.', 'success')

        except mysql.connector.Error as e:
            print(f"Error deleting all data: {e}")
            # Store the error message in the session
            flash('An error occurred while deleting all data.', 'error')

        # Redirect back to the admin page
        return redirect('/admin')

    return render_template('admin.html')


# Delete specific data
@app.route('/delete-specific-data', methods=['POST'])
def delete_specific_data():
    if request.method == 'POST':
        # Check if the user is logged in as admin
        if not is_admin_logged_in():
            # User is not logged in as admin, redirect to the login page
            return redirect('/login')

        result_id = request.form.get('result_id')

        if result_id is not None:
            # Delete the specific data from the 'conversions' table
            deletion_successful = delete_conversion_result(int(result_id))

            if deletion_successful:
                flash('Data deleted successfully.', 'success')
            else:
                flash('Failed to delete data. Data not found.', 'error')
            
    return redirect('/admin')


def delete_conversion_result(result_id):
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            user=mysql_user,
            password=mysql_password
        )
        cursor = conn.cursor()

        delete_query = "DELETE FROM conversions WHERE id = %s"
        cursor.execute(delete_query, (result_id,))
        conn.commit()

        # Update the IDs of the remaining rows
        update_query = "ALTER TABLE conversions AUTO_INCREMENT = 1"
        cursor.execute(update_query)
        conn.commit()

        cursor.close()
        conn.close()
        return True

    except Error as e:
        print(f"Error deleting conversion result: {e}")
        return False

# Logout
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return redirect('/')


if __name__ == '__main__':
    app.run()
