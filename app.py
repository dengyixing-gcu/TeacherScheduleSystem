from flask import Flask, render_template, request, jsonify
import pandas as pd
import re
from datetime import datetime, timedelta
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, '教师课表 1.xlsx')
CACHE_FILE = os.path.join(BASE_DIR, 'schedule_cache.json')

app = Flask(__name__)
SEMESTER_START = datetime(2026, 3, 2)
WEEKDAY_NAMES = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

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

def fix_encoding(text):
    """Fix mojibake encoding - Excel data was GBK encoded but read as UTF-8"""
    if not isinstance(text, str):
        return text
    # The Excel file contains GBK-encoded Chinese that was read as UTF-8
    # To fix: encode as UTF-8 to get raw bytes, then decode as GBK
    try:
        return text.encode('utf-8').decode('gbk')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text

def load_data():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    df = pd.read_excel(DATA_FILE)
    schedule = []
    
    for _, row in df.iterrows():
        teacher = str(row['教师'])
        course = str(row['课程名称'])
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
    if not os.path.exists(CACHE_FILE):
        return load_data()
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_schedule(schedule):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False)

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test_teachers.html')
def test_teachers():
    return render_template('test_teachers.html')

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

@app.route('/api/free_teachers', methods=['POST'])
def api_free_teachers():
    data = request.json
    date = data.get('date')
    start_lesson = data.get('start_lesson')
    end_lesson = data.get('end_lesson')
    
    if not date:
        return jsonify({'error': '请选择日期'}), 400
    
    week, weekday = get_week_from_date(date)
    schedule = get_schedule()
    
    all_teachers = set(item['teacher'] for item in schedule)
    
    busy_teachers = set()
    for item in schedule:
        if item['weekday'] == weekday and week in item['weeks']:
            if start_lesson and end_lesson:
                if not (item['end_lesson'] < int(start_lesson) or item['start_lesson'] > int(end_lesson)):
                    busy_teachers.add(item['teacher'])
            else:
                busy_teachers.add(item['teacher'])
    
    free_teachers = sorted(list(all_teachers - busy_teachers))
    
    return jsonify({
        'date': date,
        'week': week,
        'weekday': weekday,
        'free_teachers': free_teachers,
        'busy_teachers': sorted(list(busy_teachers))
    })

@app.route('/api/common_free_slots', methods=['POST'])
def api_common_free_slots():
    data = request.json
    teachers = data.get('teachers', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    start_lesson = data.get('start_lesson', 1)
    end_lesson = data.get('end_lesson', 11)
    
    if not teachers:
        return jsonify({'error': '请选择教师'}), 400
    
    schedule = get_schedule()
    
    teacher_schedules = {}
    for teacher in teachers:
        teacher_schedules[teacher] = [
            item for item in schedule if item['teacher'] == teacher
        ]
    
    if not start_date:
        start_date = SEMESTER_START.strftime('%Y-%m-%d')
    if not end_date:
        end_date = (SEMESTER_START + timedelta(weeks=20)).strftime('%Y-%m-%d')
    
    common_free_slots = []
    current_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
    
    while current_date <= end_datetime:
        week, weekday = get_week_from_date(current_date.strftime('%Y-%m-%d'))
        date_str = current_date.strftime('%Y-%m-%d')
        
        all_free = True
        for teacher in teachers:
            teacher_busy = False
            for item in teacher_schedules[teacher]:
                if item['weekday'] == weekday and week in item['weeks']:
                    if not (item['end_lesson'] < int(start_lesson) or item['start_lesson'] > int(end_lesson)):
                        teacher_busy = True
                        break
            if not teacher_busy:
                pass
            else:
                all_free = False
                break
        
        if all_free and len(teachers) > 0:
            teachers_checked = all(teacher in teacher_schedules for teacher in teachers)
            if teachers_checked:
                common_free_slots.append({
                    'date': date_str,
                    'week': week,
                    'weekday': weekday,
                    'weekday_name': WEEKDAY_NAMES[weekday],
                    'start_lesson': int(start_lesson),
                    'end_lesson': int(end_lesson)
                })
        
        current_date += timedelta(days=1)
    
    return jsonify({
        'teachers': teachers,
        'common_free_slots': common_free_slots
    })

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': '请输入问题'}), 400
    
    schedule = get_schedule()
    all_teachers = set(item['teacher'] for item in schedule)
    
    # 解析用户输入
    query_lower = query.lower()
    
    # 1. 查询某个老师的课表
    teacher_match = None
    for teacher in all_teachers:
        if teacher in query:
            teacher_match = teacher
            break
    
    if teacher_match:
        teacher_schedule = [item for item in schedule if item['teacher'] == teacher_match]
        if len(teacher_schedule) == 0:
            return jsonify({'response': f'抱歉，没有找到 {teacher_match} 老师的课程信息。'})
        
        response = f'{teacher_match}老师的课程安排：\n\n'
        courses = {}
        for item in teacher_schedule:
            key = item['course']
            if key not in courses:
                courses[key] = []
            courses[key].append(item)
        
        for course, items in courses.items():
            response += f'📚 {course}:\n'
            for item in items:
                response += f'  - {WEEKDAY_NAMES[item["weekday"]]} 第{item["start_lesson"]}-{item["end_lesson"]}节 ({item["location"]})\n'
            response += '\n'
        
        return jsonify({
            'response': response,
            'suggestions': [f'{teacher_match}老师周几有课', '查询其他老师']
        })
    
    # 2. 查询某个时段下，哪些老师有课/没课
    time_patterns = [
        r'(星期 [一二三四五六日]|今天 | 明天 | 后天)',
        r'(第 [1-9]|10|11) 节',
        r'(上午 | 下午 | 晚上)',
        r'(全天 | 所有时段)'
    ]
    
    has_time_ref = any(re.search(pattern, query_lower) for pattern in time_patterns)
    
    if has_time_ref or '有课' in query_lower or '没课' in query_lower or '空闲' in query_lower:
        weekday = None
        start_lesson = None
        end_lesson = None
        
        weekday_map = {'星期一': 0, '星期二': 1, '星期三': 2, '星期四': 3, '星期五': 4, '星期六': 5, '星期日': 6}
        for name, day in weekday_map.items():
            if name in query:
                weekday = day
                break
        
        if '今天' in query:
            weekday = datetime.now().weekday()
        elif '明天' in query:
            weekday = (datetime.now().weekday() + 1) % 7
        elif '后天' in query:
            weekday = (datetime.now().weekday() + 2) % 7
        
        lesson_match = re.search(r'第 (\d+)-(\d+) 节', query)
        if lesson_match:
            start_lesson = int(lesson_match.group(1))
            end_lesson = int(lesson_match.group(2))
        else:
            lesson_match = re.search(r'第 (\d+) 节', query)
            if lesson_match:
                start_lesson = int(lesson_match.group(1))
                end_lesson = int(lesson_match.group(1))
        
        if '上午' in query:
            start_lesson, end_lesson = 1, 4
        elif '下午' in query:
            start_lesson, end_lesson = 5, 8
        elif '晚上' in query:
            start_lesson, end_lesson = 9, 11
        
        if weekday is not None:
            if '没课' in query_lower or '空闲' in query_lower or '没有课' in query_lower:
                busy_teachers = set()
                for item in schedule:
                    if item['weekday'] == weekday:
                        if start_lesson and end_lesson:
                            if not (item['end_lesson'] < start_lesson or item['start_lesson'] > end_lesson):
                                busy_teachers.add(item['teacher'])
                        else:
                            busy_teachers.add(item['teacher'])
                
                free_teachers = sorted(list(all_teachers - busy_teachers))
                if len(free_teachers) == 0:
                    response = f'{WEEKDAY_NAMES[weekday]}'
                    if start_lesson and end_lesson:
                        response += f' 第{start_lesson}-{end_lesson}节'
                    response += '所有老师都有课。'
                else:
                    response = f'{WEEKDAY_NAMES[weekday]}'
                    if start_lesson and end_lesson:
                        response += f' 第{start_lesson}-{end_lesson}节'
                    response += f' 没有课的老师 ({len(free_teachers)}人):\n\n'
                    response += '、'.join(free_teachers)
                
                return jsonify({'response': response})
            else:
                busy_teachers_dict = {}
                for item in schedule:
                    if item['weekday'] == weekday:
                        if start_lesson and end_lesson:
                            if not (item['end_lesson'] < start_lesson or item['start_lesson'] > end_lesson):
                                if item['teacher'] not in busy_teachers_dict:
                                    busy_teachers_dict[item['teacher']] = []
                                busy_teachers_dict[item['teacher']].append(item)
                        else:
                            if item['teacher'] not in busy_teachers_dict:
                                busy_teachers_dict[item['teacher']] = []
                            busy_teachers_dict[item['teacher']].append(item)
                
                if len(busy_teachers_dict) == 0:
                    response = f'{WEEKDAY_NAMES[weekday]}'
                    if start_lesson and end_lesson:
                        response += f' 第{start_lesson}-{end_lesson}节'
                    response += '没有老师有课。'
                else:
                    response = f'{WEEKDAY_NAMES[weekday]}'
                    if start_lesson and end_lesson:
                        response += f' 第{start_lesson}-{end_lesson}节'
                    response += f' 有课的老师 ({len(busy_teachers_dict)}人):\n\n'
                    for teacher in sorted(busy_teachers_dict.keys()):
                        response += f'{teacher}: '
                        courses = set(item['course'] for item in busy_teachers_dict[teacher])
                        response += '、'.join(courses)
                        response += '\n'
                
                return jsonify({'response': response})
    
    # 3. 查询哪些老师在某个时段内都没有课
    common_free_match = re.search(r'哪些老师 (在.*?) 都没有课', query)
    if common_free_match or ('哪些老师' in query and '没有课' in query):
        weekday = None
        start_lesson = None
        end_lesson = None
        
        weekday_map = {'星期一': 0, '星期二': 1, '星期三': 2, '星期四': 3, '星期五': 4, '星期六': 5, '星期日': 6}
        for name, day in weekday_map.items():
            if name in query:
                weekday = day
                break
        
        lesson_match = re.search(r'第 (\d+)-(\d+) 节', query)
        if lesson_match:
            start_lesson = int(lesson_match.group(1))
            end_lesson = int(lesson_match.group(2))
        
        if '上午' in query:
            start_lesson, end_lesson = 1, 4
        elif '下午' in query:
            start_lesson, end_lesson = 5, 8
        elif '晚上' in query:
            start_lesson, end_lesson = 9, 11
        
        if weekday is not None:
            busy_teachers = set()
            for item in schedule:
                if item['weekday'] == weekday:
                    if start_lesson and end_lesson:
                        if not (item['end_lesson'] < start_lesson or item['start_lesson'] > end_lesson):
                            busy_teachers.add(item['teacher'])
                    else:
                        busy_teachers.add(item['teacher'])
            
            free_teachers = sorted(list(all_teachers - busy_teachers))
            response = f'{WEEKDAY_NAMES[weekday]}'
            if start_lesson and end_lesson:
                response += f' 第{start_lesson}-{end_lesson}节'
            response += f' 没有课的老师:\n\n'
            if len(free_teachers) == 0:
                response += '该时段所有老师都有课。'
            else:
                response += '、'.join(free_teachers)
            return jsonify({'response': response})
    
    return jsonify({
        'response': '抱歉，我暂时无法理解您的问题。我可以帮您:\n\n1. 查询某个老师的课表（例如："宁辉老师有什么课"）\n2. 查询某个时段哪些老师有课（例如："星期一上午哪些老师有课"）\n3. 查询某个时段哪些老师没课（例如："星期三下午哪些老师没课"）\n4. 查询共同空闲时段（例如："哪些老师星期五都没有课"）',
        'suggestions': ['蔡沂老师的课表', '星期一上午哪些老师有课', '星期三下午哪些老师没课']
    })

@app.route('/health')
def health():
    """健康检查端点"""
    return jsonify({'status': 'healthy', 'service': 'teacher-schedule-system'})

if __name__ == '__main__':
    load_data()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
