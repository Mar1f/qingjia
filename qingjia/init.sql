CREATE TABLE leave_records (
    id INT PRIMARY KEY AUTO_INCREMENT,
    student_id VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    photo_url VARCHAR(255) NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    leave_data DATE NOT NULL
);
