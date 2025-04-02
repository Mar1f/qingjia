import os
import pymysql
import tempfile
import shutil
from zipfile import ZipFile
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory, after_this_request
from qcloud_cos import CosConfig, CosS3Client
from openpyxl import Workbook
from datetime import datetime

# 加载环境变量
load_dotenv()

app = Flask(__name__,
            static_folder='static',
            template_folder='templates',
            static_url_path='')

# 腾讯云COS配置
cos_config = CosConfig(
    Region=os.getenv('COS_REGION'),
    SecretId=os.getenv('COS_SECRET_ID'),
    SecretKey=os.getenv('COS_SECRET_KEY')
)
cos_client = CosS3Client(cos_config)

# 数据库配置
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'leave_peo'),
    'password': os.getenv('DB_PASSWORD', '123456'),
    'database': os.getenv('DB_NAME', 'leave_peo'),
    'charset': 'utf8mb4'
}


def get_db_connection():
    return pymysql.connect(**db_config)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/submit', methods=['POST'])
def submit_application():
    try:
        # 获取表单数据
        student_id = request.form.get('student_id')
        name = request.form.get('name')
        reason = request.form.get('reason')
        leave_date = request.form.get('leave_date')
        photo = request.files.get('photo')

        # 基本验证
        required_fields = [student_id, name, reason, leave_date, photo]
        if not all(required_fields):
            return jsonify({'status': 'error', 'message': '所有字段必须填写'}), 400

        # 日期验证
        try:
            datetime.strptime(leave_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': 'error', 'message': '日期格式错误（YYYY-MM-DD）'}), 400

        # 文件验证
        if not photo.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            return jsonify({'status': 'error', 'message': '仅支持PNG/JPG格式图片'}), 400

        # 生成唯一文件名
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_ext = os.path.splitext(photo.filename)[1].lower()
        cos_filename = f"{student_id}_{name}_{timestamp}{file_ext}"
        cos_path = f"photos/{cos_filename}"

        # 上传到腾讯云COS
        cos_client.put_object(
            Bucket=os.getenv('COS_BUCKET'),
            Body=photo,
            Key=cos_path,
            StorageClass='STANDARD',
            EnableMD5=True
        )

        # 构建图片URL
        photo_url = f"https://{os.getenv('COS_BUCKET')}.cos.{os.getenv('COS_REGION')}.myqcloud.com/{cos_path}"

        # 存入数据库
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                sql = """INSERT INTO leave_records 
                        (student_id, name, reason, leave_date, photo_url)
                        VALUES (%s, %s, %s, %s, %s)"""
                cursor.execute(sql, (student_id, name, reason, leave_date, photo_url))
            connection.commit()
        finally:
            connection.close()

        return jsonify({
            'status': 'success',
            'message': '申请提交成功',
            'photo_url': photo_url
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'服务器错误: {str(e)}'
        }), 500


@app.route('/api/export')
def export_data():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # 确保日期格式正确并转换为日期对象
        def validate_date(date_str):
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            except ValueError:
                return None

        start_date_obj = validate_date(start_date)
        end_date_obj = validate_date(end_date)

        if not start_date_obj or not end_date_obj:
            return jsonify({'status': 'error', 'message': '必须提供开始和结束日期'}), 400

        if start_date_obj > end_date_obj:
            return jsonify({'status': 'error', 'message': '开始日期不能晚于结束日期'}), 400

        # 修改查询语句，使用严格的日期范围过滤
        connection = get_db_connection()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                query = """
                    SELECT * FROM leave_records 
                    WHERE leave_date >= %s AND leave_date <= %s 
                    ORDER BY leave_date DESC
                """
                cursor.execute(query, (start_date_obj, end_date_obj))
                records = cursor.fetchall()
        finally:
            connection.close()

        # 创建临时工作目录
        temp_dir = tempfile.mkdtemp()
        photos_dir = os.path.join(temp_dir, '22级软件工程ISEC第五周假条')
        os.makedirs(photos_dir, exist_ok=True)

        # 下载所有关联图片
        for record in records:
            try:
                # 从URL解析COS对象键
                photo_url = record['photo_url']
                bucket_prefix = f"{os.getenv('COS_BUCKET')}.cos.{os.getenv('COS_REGION')}.myqcloud.com/"
                key = photo_url.split(bucket_prefix)[1]

                # 下载图片
                response = cos_client.get_object(
                    Bucket=os.getenv('COS_BUCKET'),
                    Key=key
                )

                # 保存到本地
                filename = f"{record['student_id']}_{os.path.basename(key)}"
                local_path = os.path.join(photos_dir, filename)
                with open(local_path, 'wb') as f:
                    f.write(response['Body'].get_raw_stream().read())
            except Exception as e:
                app.logger.error(f"图片下载失败：{str(e)}")

        # 生成Excel文件
        wb = Workbook()
        ws = wb.active
        ws.title = "请假记录"
        headers = ['学号', '专业', '姓名', '请假日期', '请假原因']
        ws.append(headers)

        for record in records:
            ws.append([
                record['student_id'],
                '软件工程ISEC',
                record['name'],
                record['leave_date'].strftime('%Y-%m-%d'),
                record['reason']
            ])

        excel_path = os.path.join(temp_dir, '22级软件工程ISEC第五周请假汇总表.xlsx')
        wb.save(excel_path)

        # 创建ZIP压缩包
        zip_path = os.path.join(temp_dir, 'export.zip')
        with ZipFile(zip_path, 'w') as zipf:
            # 添加Excel文件
            zipf.write(excel_path, arcname='22级软件工程ISEC第五周请假汇总表.xlsx')
            # 添加图片目录
            for root, dirs, files in os.walk(photos_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.join('22级软件工程ISEC第五周假条', file)
                    zipf.write(file_path, arcname=arcname)

        # 设置清理回调
        @after_this_request
        def cleanup(response):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                app.logger.error(f"临时文件清理失败: {str(e)}")
            return response

        # 生成下载文件名
        filename = f"22级软件工程ISEC第五周假条.zip"
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'导出失败: {str(e)}'
        }), 500


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


def init_database():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leave_records (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    student_id VARCHAR(20) NOT NULL,
                    name VARCHAR(50) NOT NULL,
                    reason TEXT NOT NULL,
                    leave_date DATE NOT NULL,
                    photo_url VARCHAR(255) NOT NULL,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()


# 在app.py中添加测试路由
@app.route('/ping')
def ping():
    return f"服务运行在端口 {os.getenv('FLASK_PORT', 23456)}"


@app.route('/today')
def show_today():
    try:
        connection = get_db_connection()
        today = datetime.now().strftime('%Y-%m-%d')
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT student_id, name, reason, photo_url 
                FROM leave_records 
                WHERE leave_date = %s 
                ORDER BY create_time DESC
            """, (today,))
            records = cursor.fetchall()
        connection.close()
        return render_template('today.html', records=records, today=today)
    except Exception as e:
        return render_template('error.html', message=f'数据加载失败: {str(e)}')


if __name__ == '__main__':
    init_database()
    app.run(
        host='0.0.0.0', port=23456,
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    )