import os
import re
import random
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-change-it-later'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB limit

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# --- Models ---
class Module(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    questions = db.relationship('Question', backref='module', lazy=True, cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey('module.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), nullable=False) # 'single', 'multiple', 'numerical'
    image_path = db.Column(db.String(255), nullable=True) 
    explanation = db.Column(db.Text, nullable=True)
    options = db.relationship('Option', backref='question', lazy=True, cascade='all, delete-orphan')

class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)

class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(100), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('module.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    mode = db.Column(db.String(20), nullable=False) # 'exam' or 'practice'
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    module_obj = db.relationship('Module', backref=db.backref('attempts', lazy=True))

with app.app_context():
    db.create_all()

# --- Auth Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'WhiteDevil' and password == 'CSA@1437':
            session['logged_in'] = True
            flash('Welcome back, WhiteDevil!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('home'))

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        if name:
            new_module = Module(name=name, description=description)
            db.session.add(new_module)
            db.session.commit()
            flash('Module created successfully!', 'success')
            return redirect(url_for('upload'))
    modules = Module.query.all()
    return render_template('upload.html', modules=modules)

@app.route('/edit_module/<int:module_id>')
@login_required
def edit_module(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        flash('Module not found.', 'error')
        return redirect(url_for('upload'))
    return render_template('edit_module.html', module=module)

@app.route('/edit_module/<int:module_id>/add_question', methods=['POST'])
@login_required
def add_question(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return redirect(url_for('upload'))
    
    text = request.form.get('text')
    explanation = request.form.get('explanation')
    q_type = request.form.get('type')
    
    # Handle image upload
    image_file = request.files.get('image')
    image_path = None
    if image_file and image_file.filename != '':
        filename = secure_filename(image_file.filename)
        # Using module_id and q_type as prefix for uniqueness could be good, but we'll prepend an id or similar
        import uuid
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        image_path = unique_filename
        
    question = Question(module_id=module.id, text=text, type=q_type, image_path=image_path, explanation=explanation)
    db.session.add(question)
    db.session.commit() # Commit to get question.id

    if q_type in ['single', 'multiple']:
        for i in range(1, 5):
            opt_text = request.form.get(f'option_{i}')
            if opt_text and opt_text.strip():
                is_correct = bool(request.form.get(f'is_correct_{i}'))
                opt = Option(question_id=question.id, text=opt_text.strip(), is_correct=is_correct)
                db.session.add(opt)
    elif q_type == 'numerical':
        num_ans = request.form.get('numerical_answer')
        if num_ans:
            # We store the numerical answer in the Option table as a correct text option
            opt = Option(question_id=question.id, text=str(num_ans), is_correct=True)
            db.session.add(opt)
            
    db.session.commit()
    flash('Question added successfully!', 'success')
    return redirect(url_for('edit_module', module_id=module.id))

@app.route('/delete_question/<int:question_id>', methods=['POST'])
@login_required
def delete_question(question_id):
    question = db.session.get(Question, question_id)
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('upload'))
    
    module_id = question.module_id
    
    # Delete associated image file if it exists
    if question.image_path:
        image_full_path = os.path.join(app.config['UPLOAD_FOLDER'], question.image_path)
        if os.path.exists(image_full_path):
            os.remove(image_full_path)
            
    db.session.delete(question)
    db.session.commit()
    flash('Question deleted successfully!', 'success')
    return redirect(url_for('edit_module', module_id=module_id))

@app.route('/edit_question/<int:question_id>', methods=['GET', 'POST'])
@login_required
def edit_question(question_id):
    question = db.session.get(Question, question_id)
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('upload'))
    
    if request.method == 'POST':
        question.text = request.form.get('text')
        question.type = request.form.get('type')
        question.explanation = request.form.get('explanation')
        
        # Handle image
        remove_image = request.form.get('remove_image')
        new_image = request.files.get('image')
        
        if remove_image or (new_image and new_image.filename != ''):
            if question.image_path:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], question.image_path)
                if os.path.exists(old_path):
                    os.remove(old_path)
                question.image_path = None
        
        if new_image and new_image.filename != '':
            from werkzeug.utils import secure_filename
            import uuid
            filename = secure_filename(new_image.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            new_image.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            question.image_path = unique_filename

        # Update options: Delete old and add new
        Option.query.filter_by(question_id=question.id).delete()
        
        if question.type in ['single', 'multiple']:
            for i in range(1, 5):
                opt_text = request.form.get(f'option_{i}')
                if opt_text and opt_text.strip():
                    is_correct = bool(request.form.get(f'is_correct_{i}'))
                    opt = Option(question_id=question.id, text=opt_text.strip(), is_correct=is_correct)
                    db.session.add(opt)
        elif question.type == 'numerical':
            num_ans = request.form.get('numerical_answer')
            if num_ans:
                opt = Option(question_id=question.id, text=str(num_ans), is_correct=True)
                db.session.add(opt)
        
        db.session.commit()
        flash('Question updated successfully!', 'success')
        return redirect(url_for('edit_module', module_id=question.module_id))
    
    return render_template('edit_question.html', question=question)

@app.route('/edit_module/<int:module_id>/smart_paste', methods=['POST'])
@login_required
def smart_paste(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return redirect(url_for('upload'))
        
    text = request.form.get('pasted_text', '')
    chunks = re.split(r'\n\s*\n', text.strip())
    questions_added = 0
    
    for chunk in chunks:
        lines = [line.strip() for line in chunk.split('\n') if line.strip()]
        if not lines: continue
        
        question_lines = []
        options = {}
        correct_letter = None
        explanation = None
        
        opt_re = re.compile(r'^([A-E])[\.\)]\s*(.*)', re.IGNORECASE)
        exp_re = re.compile(r'^(?:Explanation|Exp)[:\s\-]*(.*)', re.IGNORECASE)
        
        for line in lines:
            c_match = re.search(r'(?:Correct(?: Answer)?|Answer)(?:\s*is)?[:\s\-]*(?:Option\s*)?([A-E])', line, re.IGNORECASE)
            if c_match and not opt_re.match(line):
                correct_letter = c_match.group(1).upper()
                continue
                
            opt_match = opt_re.match(line)
            if opt_match:
                options[opt_match.group(1).upper()] = opt_match.group(2)
                continue

            exp_match = exp_re.match(line)
            if exp_match:
                explanation = exp_match.group(1).strip()
                continue
                
            if re.search(r'next question is', line, re.IGNORECASE):
                continue
            question_lines.append(line)
            
        if question_lines and options and correct_letter:
            q_text = '\n'.join(question_lines)
            q_text = re.sub(r'^\d+\.\s*', '', q_text).strip()
            
            q = Question(module_id=module.id, text=q_text, type='single', explanation=explanation)
            db.session.add(q)
            db.session.commit()
            
            for letter in sorted(options.keys()):
                opt_text = options[letter]
                is_correct = (letter == correct_letter)
                opt = Option(question_id=q.id, text=opt_text, is_correct=is_correct)
                db.session.add(opt)
            
            db.session.commit()
            questions_added += 1

    if questions_added > 0:
        flash(f'Successfully imported {questions_added} question(s)!', 'success')
    else:
        flash('Could not parse any questions. Please check the format.', 'error')
        
    return redirect(url_for('edit_module', module_id=module.id))

@app.route('/practice')
def practice():
    modules = Module.query.all()
    return render_template('practice.html', modules=modules)

@app.route('/history')
@login_required
def history():
    attempts = Attempt.query.order_by(Attempt.timestamp.desc()).all()
    return render_template('history.html', attempts=attempts)

@app.route('/delete_attempt/<int:attempt_id>', methods=['POST'])
@login_required
def delete_attempt(attempt_id):
    attempt = db.session.get(Attempt, attempt_id)
    if attempt:
        db.session.delete(attempt)
        db.session.commit()
        flash('Attempt deleted.', 'success')
    return redirect(url_for('history'))

@app.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    db.session.query(Attempt).delete()
    db.session.commit()
    flash('All history cleared.', 'success')
    return redirect(url_for('history'))

@app.route('/practice_exam')
def practice_exam():
    modules = Module.query.all()
    # Reusing practice.html but with a different title and target
    return render_template('practice.html', modules=modules, mode='exam')

@app.route('/exam/<int:module_id>')
def exam(module_id):
    module = db.session.get(Module, module_id)
    if not module or not module.questions:
        flash('Module not found or has no questions.', 'error')
        return redirect(url_for('practice_exam'))
        
    questions = list(module.questions)
    random.shuffle(questions)
    
    for q in questions:
        shuffled_opts = list(q.options)
        random.shuffle(shuffled_opts)
        q.shuffled_options = shuffled_opts
        
    return render_template('exam.html', module=module, questions=questions)

@app.route('/quiz/<int:module_id>')
def quiz(module_id):
    module = db.session.get(Module, module_id)
    if not module or not module.questions:
        flash('Module not found or has no questions.', 'error')
        return redirect(url_for('practice'))
        
    questions = list(module.questions)
    random.shuffle(questions)
    
    for q in questions:
        shuffled_opts = list(q.options)
        random.shuffle(shuffled_opts)
        q.shuffled_options = shuffled_opts
        
    return render_template('quiz.html', module=module, questions=questions)

@app.route('/quiz/<int:module_id>/submit', methods=['POST'])
def submit_quiz(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return redirect(url_for('practice'))
    
    score = 0
    total = len(module.questions)
    
    for q in module.questions:
        if q.type == 'single':
            ans_id = request.form.get(f'q_{q.id}')
            if ans_id:
                opt = db.session.get(Option, int(ans_id))
                if opt and opt.is_correct:
                    score += 1
        elif q.type == 'multiple':
            ans_ids = request.form.getlist(f'q_{q.id}[]')
            correct_opts = [o for o in q.options if o.is_correct]
            correct_ids = [str(o.id) for o in correct_opts]
            # Check if selected arrays match perfectly
            if set(ans_ids) == set(correct_ids) and len(ans_ids) > 0:
                score += 1
        elif q.type == 'numerical':
            ans_val = request.form.get(f'q_{q.id}')
            correct_opt = next((o for o in q.options if o.is_correct), None)
            if ans_val and correct_opt:
                try:
                    if float(ans_val) == float(correct_opt.text):
                        score += 1
                except ValueError:
                    pass
    
    # Track attempt
    student_name = request.form.get('student_name', 'Anonymous')
    mode = request.form.get('mode', 'practice')
    percentage = (score / total * 100) if total > 0 else 0
    
    attempt = Attempt(
        student_name=student_name,
        module_id=module.id,
        score=score,
        total=total,
        percentage=round(percentage, 2),
        mode=mode
    )
    db.session.add(attempt)
    db.session.commit()
                    
    return render_template('quiz_result.html', module=module, score=score, total=total, percentage=round(percentage, 2))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
