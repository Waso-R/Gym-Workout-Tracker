from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, NumberRange

class SignupForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField("Sign Up")

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log In")

class WorkoutForm(FlaskForm):
    workout_type = StringField("Workout Type", validators=[DataRequired()])
    reps = IntegerField("Reps", validators=[DataRequired()])
    sets = IntegerField("Sets", validators=[DataRequired()])
    weight = IntegerField("Weight (kg)", validators=[DataRequired()])
    submit = SubmitField("Log Workout")

class SplitForm(FlaskForm):
    days_per_week = IntegerField("Days per Week", validators=[DataRequired(), NumberRange(min=1, max=7, message="Enter a number between 1 and 7")])
    submit = SubmitField("Generate Split")
