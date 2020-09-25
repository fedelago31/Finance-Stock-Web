import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    data_list = []
    totalsum = 0
    user_portfolio = db.execute("SELECT * FROM user_stocks WHERE user_id=:userid", userid=session["user_id"])
    user_cash = db.execute("SELECT cash FROM users WHERE id=:userid", userid=session["user_id"])
    user_cash = float(user_cash[0]["cash"])

    for row in user_portfolio:
        stock = lookup(row["stock_id"])
        total = float(row["amount"]) * float(stock["price"])
        #add total to total sum before converting it to a string
        totalsum += total
        #format total to usd string
        total = usd(total)

        item = {
            "symbol": row["stock_id"],
            "name": stock["name"],
            "amount": row["amount"],
            "price": stock["price"],
            "total": total,
            }

        data_list.append(item)

    total_cash = totalsum + user_cash
    total_cash = usd(total_cash)
    user_cash = usd(user_cash)

    return render_template("index.html", data_list=data_list, user_cash=user_cash, total_cash=total_cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        #check for empty values
        if not request.form.get("symbol"):
            return apology("Provide a symbol...", 410)
        if not request.form.get("amount"):
            return apology("Provide amount...", 410)

        #declare some variables for easy access
        symbol = request.form.get("symbol")
        amount = request.form.get("amount")
        trans_type = "buy"

        #call the api to have the stock object
        stock = lookup(symbol)

        if stock == None:
            return apology("Invalid symbol", 410)

        #get the cash
        user_cash = db.execute("SELECT cash FROM users WHERE id=:userid", userid=session["user_id"])
        #store the cash in a variable for easy access
        user_cash = float(user_cash[0]["cash"])
        #store the price of the transaction
        price = float(stock["price"]) * float(amount)

        #check for enough cash
        if price <= user_cash:
            #check if the user already have stocks with that symbol
            user_data = db.execute("SELECT * FROM user_stocks WHERE user_id=:userid AND stock_id=:stockid", userid=session["user_id"], stockid=stock["symbol"])
            if not user_data:
                db.execute("INSERT INTO user_stocks (user_id, stock_id, amount) VALUES (?, ?, ?)", session["user_id"], stock["symbol"], amount)
            else:
                user_stocks = float(user_data[0]["amount"]) + float(amount)
                db.execute("UPDATE user_stocks SET amount=:newamount WHERE id=:rowid", newamount=user_stocks, rowid=user_data[0]["id"])

            #insert the transction on the db
            db.execute("INSERT INTO transactions (user_id, symbol, amount, price, type) VALUES (?, ?, ?, ?, ?)",session["user_id"], stock["symbol"], amount, stock["price"], trans_type)
            #update the user cash in the db.
            db.execute("UPDATE users SET cash=:newcash WHERE id=:userid", newcash=user_cash - price, userid=session["user_id"])
            #return 0
            return redirect("/")
        else:
            return apology("You can not afford it", 410)

#END OF BUY


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""


    user_history = db.execute("SELECT * FROM transactions WHERE user_id=:userid", userid=session["user_id"])

    return render_template("history.html", data_list=user_history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        if stock == None:
            return apology("Symbol doesnt exist", 410)
        else:
            return render_template("quote.html", name=stock["name"], price=stock["price"], symbol=stock["symbol"])
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        #check for empty input
        if not request.form.get("username"):
            return apology("No username given", 403)
        if not request.form.get("password"):
            return apology("No password given", 403)

        username = request.form.get("username")
        password = request.form.get("password")

        #check for matching passwords
        if password != request.form.get("confirm-password"):
            return apology("Password should match", 409)
        else:
            #check for existing user
            table = db.execute("SELECT * FROM users WHERE username = :username", username=username)

            if len(table) > 0:
                return apology("username already taken", 408)
            else:
                #insert the user in the sql
                hashpassword = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
                db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hashpassword)
                return redirect("/")




@app.route("/add_money", methods=["GET", "POST"])
@login_required
def add_money():
    """Add money to account"""

    if request.method == "GET":
        return render_template("add_money.html")
    else:

        if not request.form.get("amount"):
            return apology("Insert a value", 412 )

        amount = float(request.form.get("amount"))

        if amount < 0:
            return apology("You can only add positive numbers", 412)

        user_data=db.execute("SELECT * FROM users WHERE id=:userid", userid=session["user_id"])

        user_cash=float(user_data[0]["cash"])
        new_balance = user_cash + amount

        if new_balance > 99999:
            return apology("The maximum you can add is 99.999", 412)
        else:
            db.execute("UPDATE users SET cash=:newcash WHERE id=:userid", newcash=new_balance, userid=session["user_id"])
            return redirect("/")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        #get the users stocks symbols
        user_portfolio = db.execute("SELECT * FROM user_stocks WHERE user_id=:userid", userid=session["user_id"])
        symbols = []

        for row in user_portfolio:
            symbols.append(row["stock_id"])

        return render_template("sell.html", symbols=symbols)

    else:
        #check for empty or null values
        if not request.form.get("shares"):
            return apology("Provide a number of shares", 411)
        if not request.form.get("symbol"):
            return apology("Select a symbol to sell", 411)

        #Getting users info such like his portfolio and his cash.
        user_data = db.execute("SELECT * FROM users WHERE id=:userid", userid=session["user_id"])
        user_cash = float(user_data[0]["cash"])

        #get the share info
        symbol = request.form.get("symbol")
        stock_data = lookup(symbol)

        #amount of shares user want to sell
        amount = int(request.form.get("shares"))
        if amount <= 0:
            return apology("Dont provide a negative value or 0", 411)

        #check if it has enough
        user_stocks = db.execute("SELECT * FROM user_stocks WHERE user_id=:userid AND stock_id=:stockid", userid=session["user_id"], stockid=symbol)
        user_amount = int(user_stocks[0]["amount"])
        #the id of the row which contains the data.
        portfolio_id = user_stocks[0]["id"]

        if amount > user_amount:
            return apology("you dont have enough", 411)

        #starting transaction, confirm the price of the amount of shares, updating the amount of shares of user, and its cash
        sell_price = stock_data["price"] * amount
        user_cash = user_cash + sell_price
        user_amount = user_amount - amount
        trans_type = "sell"
        amount = amount * -1

        #update the database starting with the user portfolio, his money, and lastly inserting the transaction in the database.
        if user_amount == 0:
            db.execute("DELETE FROM user_stocks WHERE id=:portfolioid", portfolioid=portfolio_id)
        else:
            db.execute("UPDATE user_stocks SET amount=:newamount WHERE id=:portfolioid", newamount=user_amount, portfolioid=portfolio_id)

        #update user cash
        db.execute("UPDATE users SET cash=:newcash WHERE id=:userid", newcash=user_cash, userid=session["user_id"])

        #insert the transaction in the db
        db.execute("INSERT INTO transactions (user_id, symbol, amount, price, type) VALUES (?, ?, ?, ?, ?)", session["user_id"], symbol, amount, stock_data["price"], trans_type)
        return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
