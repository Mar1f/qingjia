function submitForm() {
    const formData = new FormData();
    formData.append('student_id', document.getElementById('student_id').value);
    formData.append('name', document.getElementById('name').value);
    formData.append('reason', document.getElementById('reason').value);
    formData.append('photo', document.getElementById('photo').files[0]);
    formData.append('leave_date', document.getElementById('leave_date').value);

    fetch('/api/submit', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        showMessage('提交成功！', 'success');
        document.getElementById('leaveForm').reset();
    })
    .catch(error => {
        showMessage('提交失败，请重试', 'error');
    });
}

function exportData() {
    const startDate = document.getElementById('start_date').value;
    const endDate = document.getElementById('end_date').value;

    // 构建查询参数
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    window.location.href = '/api/export';
}

function showMessage(text, type) {
    const msgDiv = document.getElementById('message');
    msgDiv.className = `message ${type}`;
    msgDiv.textContent = text;
    setTimeout(() => msgDiv.textContent = '', 3000);
}
