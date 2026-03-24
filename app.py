from flask import Flask, render_template, request, jsonify
import pandas as pd
import re
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)

SEMESTER_START = datetime(2026, 3, 2)
DATA_FILE = '教师课表 1.xlsx'
CACHE_FILE = 'schedule_cache.json'

def parse_weeks(week_str):
    weeks = []
    week_str = week_str.strip('{}')
    week_str = week_str.replace(',', ',')
    parts = week_str.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        clean_part = part.replace('(单)', '').replace('(双)', '')
        clean_part = clean_part.strip()
        
        match = re.match(r'(\d+)\s*-\s*(\d+)\s*周', clean_part)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            week_range = list(range(start, end + 1))
            if '(单)' in part:
                week_range = [w for w in week_range if w % 2 == 1]
            elif '(双)' in part:
                week_range = [w for w in week_range if w % 2 == 0]
            weeks.extend(week_range)
        else:
            match = re.match(r'(\d+)\s*周', clean_part)
            if match:
                week = int(match.group(1))
                weeks.append(week)
    
    return sorted(set(weeks))

def parse_time_slot(time_str):
    match = re.match(r'星期.第\s*(\d+)-(\d+)\s*节\{(.+)\}', time_str)
    if match:
        weekday_char = match.group(0)[2]
        weekday_map = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6}
        weekday = weekday_map.get(weekday_char, 0)
        start_lesson = int(match.group(1))
        end_lesson = int(match.group(2))
        weeks = parse_weeks(match.group(3))
        return {
            'weekday': weekday,
            'start_lesson': start_lesson,
            'end_lesson': end_lesson,
            'weeks': weeks
        }
    return None

def get_week_from_date(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    days_diff = (date - SEMESTER_START).days
    week = days_diff // 7 + 1
    return week, date.weekday()

def load_data():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    df = pd.read_excel(DATA_FILE)
    schedule = []
    
    for _, row in df.iterrows():
        teacher = row['教师']
        course = row['课程名称']
        times = str(row['时间']).split(';')
        locations = str(row['地点']).split(';')
        classes = str(row['班级组成'])
        
        for i, time_str in enumerate(times):
            time_slot = parse_time_slot(time_str.strip())
            if time_slot:
                location = locations[i].strip() if i < len(locations) else ''
                schedule.append({
                    'id': f"{teacher}_{course}_{i}",
                    'teacher': teacher,
                    'course': course,
                    'weekday': time_slot['weekday'],
                    'start_lesson': time_slot['start_lesson'],
                    'end_lesson': time_slot['end_lesson'],
                    'weeks': time_slot['weeks'],
                    'location': location,
                    'classes': classes
                })
    
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False)
    
    return schedule

def get_schedule():
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_schedule(schedule):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/schedule')
def api_schedule():
    schedule = get_schedule()
    return jsonify(schedule)

@app.route('/api/teachers')
def api_teachers():
    schedule = get_schedule()
    teachers = sorted(set(item['teacher'] for item in schedule))
    return jsonify(teachers)

@app.route('/api/teacher/<name>')
def api_teacher_schedule(name):
    schedule = get_schedule()
    teacher_schedule = [item for item in schedule if item['teacher'] == name]
    return jsonify(teacher_schedule)

@app.route('/api/date_schedule', methods=['POST'])
def api_date_schedule():
    data = request.json
    date = data.get('date')
    start_lesson = data.get('start_lesson')
    end_lesson = data.get('end_lesson')
    
    if not date:
        return jsonify({'error': '请选择日期'}), 400
    
    week, weekday = get_week_from_date(date)
    schedule = get_schedule()
    
    day_schedule = [
        item for item in schedule
        if item['weekday'] == weekday and week in item['weeks']
    ]
    
    if start_lesson and end_lesson:
        start_lesson = int(start_lesson)
        end_lesson = int(end_lesson)
        day_schedule = [
            item for item in day_schedule
            if not (item['end_lesson'] < start_lesson or item['start_lesson'] > end_lesson)
        ]
    
    return jsonify({
        'date': date,
        'week': week,
        'weekday': weekday,
        'schedule': day_schedule
    })

@app.route('/api/lesson/<weekday>/<lesson>')
def api_lesson_schedule(weekday, lesson):
    schedule = get_schedule()
    lesson_schedule = [
        item for item in schedule
        if item['weekday'] == int(weekday) and item['start_lesson'] <= int(lesson) <= item['end_lesson']
    ]
    return jsonify(lesson_schedule)

@app.route('/api/reschedule', methods=['POST'])
def api_reschedule():
    data = request.json
    schedule = get_schedule()
    
    old_date = data.get('old_date')
    old_start = data.get('old_start_lesson')
    old_end = data.get('old_end_lesson')
    old_teacher = data.get('old_teacher')
    
    new_date = data.get('new_date')
    new_start = data.get('new_start_lesson')
    new_end = data.get('new_end_lesson')
    new_weekday = data.get('new_weekday')
    new_location = data.get('new_location')
    
    old_week, old_weekday = get_week_from_date(old_date)
    new_week, _ = get_week_from_date(new_date)
    
    found = False
    for item in schedule:
        if (item['teacher'] == old_teacher and 
            item['weekday'] == old_weekday and 
            item['start_lesson'] == int(old_start) and
            item['end_lesson'] == int(old_end) and
            old_week in item['weeks']):
            item['weekday'] = int(new_weekday)
            item['start_lesson'] = int(new_start)
            item['end_lesson'] = int(new_end)
            if new_location:
                item['location'] = new_location
            if new_week:
                item['weeks'] = [new_week]
            found = True
            break
    
    if found:
        save_schedule(schedule)
        return jsonify({'success': True, 'message': '调课成功'})
    else:
        return jsonify({'success': False, 'message': '未找到原课程'}), 400

@app.route('/api/add_course', methods=['POST'])
def api_add_course():
    data = request.json
    schedule = get_schedule()
    
    new_course = {
        'id': data.get('id', f"new_{len(schedule)}"),
        'teacher': data['teacher'],
        'course': data['course'],
        'weekday': int(data['weekday']),
        'start_lesson': int(data['start_lesson']),
        'end_lesson': int(data['end_lesson']),
        'weeks': [int(w) for w in data['weeks']],
        'location': data['location'],
        'classes': data.get('classes', '')
    }
    
    schedule.append(new_course)
    save_schedule(schedule)
    return jsonify({'success': True, 'schedule': schedule})

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

@app.route('/health')
def health():
    """健康检查端点"""
    return jsonify({'status': 'healthy', 'service': 'teacher-schedule-system'})

if __name__ == '__main__':
    load_data()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
