import os
from pydicom import dcmread
import matplotlib
matplotlib.use('TkAgg')  # 切换到 TkAgg 后端
import matplotlib.pyplot as plt
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
from fpdf import FPDF  # 用于将 .rpt 文件转换为 PDF
from datetime import datetime
import time

# 定义函数来处理单个DICOM文件
def process_dicom_file(dicom_path, output_dir):
    # 读取DICOM文件
    ds = dcmread(dicom_path)
    
    # 提取用户信息
    patient_name = ds.get('PatientName', 'Unknown')
    study_date = ds.get('StudyDate', 'Unknown')
    study_time = ds.get('StudyTime', 'Unknown')[:6]
    study_date_time = datetime.strptime(study_date + study_time, "%Y%m%d%H%M%S").strftime('%Y-%m-%d %H:%M:%S')
    """
    # 解析日期字符串
    date_obj = datetime.strptime(study_date, '%Y%m%d')
    # 添加默认的时分秒
    study_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
    """
    patient_id = ds.get('PatientID', 'Unknown')
    patient_sex = ds.get('PatientSex', 'Unknown')
    study_desc = ds.get('StudyDescription', 'Unknown')
    patient_phone, patient_address = study_desc.split(';')
    if(not(patient_phone)): patient_phone = 'Unknown'
    if(not(patient_address)): patient_address = 'Unknown'
    #patient_phone = ds.get('PatientTelephoneNumbers', 'Unknown')  # 注意这里可能不是标准DICOM标签
    #patient_address = ds.get('PatientAddress', 'Unknown')  # 注意这里可能不是标准DICOM标签
    device_code = ds.get('DeviceSerialNumber', 'Unknown')
    data_id = ds.get('SOPInstanceUID', 'Unknown')
    report_title = str(patient_name) + " DR检查报告单" #ds.get('SeriesDescription', 'Unknown')
    body_part = bytes(ds.get('BodyPartExamined', 'Unknown'), 'latin_1').decode('cp936')
    
    if patient_sex == 'M':
        patient_sex = '1'
    elif patient_sex == 'F':
        patient_sex = '2'
    else:
        patient_sex = '0'

    print(f"Patient Name: {patient_name}")
    print(f"Study Date: {study_date_time}")
    print(f"Patient ID: {patient_id}")
    print(f"Patient Sex: {patient_sex}")
    print(f"Patient Phone: {patient_phone}")
    print(f"Patient Address: {patient_address}")
    print(f"Device Code: {device_code}")
    print(f"Data ID: {data_id}")
    print(f"Report Title: {report_title}")
    print(f"Body Part Examined: {body_part}")
    
    # 将DICOM图像转换为PNG
    cmd_part = r"dcmtk-tools\dcm2pnm.exe +Wm +on"
    #png_filename = os.path.join(output_dir, f"{os.path.basename(dicom_path)}.png")
    png_filename = os.path.splitext(os.path.basename(dicom_path))[0] + ".png"
    png_filename = os.path.join(output_dir, png_filename)
    cmd_line = cmd_part + " " + dicom_path + " " + png_filename
    os.system(cmd_line)
    time.sleep(3) # wait some time until png file is generated ok.
    """
    image_data = ds.pixel_array
    plt.imshow(image_data, cmap=plt.cm.bone)  # 使用骨色映射
    plt.axis('off')  # 关闭坐标轴
    # 保存PNG图像到指定目录
    plt.savefig(png_filename, bbox_inches='tight', pad_inches=0)
    """
    return png_filename, patient_name, study_date_time, patient_id, patient_sex, patient_phone, patient_address, device_code, data_id, report_title

# 将 .rpt 文件转换为 PDF
def convert_rpt_to_pdf(rpt_path, pdf_path):
    with open(rpt_path, 'r') as file:
        content = file.read()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, content)
    pdf.output(pdf_path)

# 定义函数来上传文件
def upload_files(files, api_url):
    files_list = []
    for file_path, patient_name, study_date, patient_id, patient_sex, patient_phone, patient_address, device_code, data_id, report_title in files:
        if os.path.basename(file_path).endswith("png"):
        # 打开图片文件
            print(f"Files to be uploaded:: {file_path} ")
            files_list.append(('xphoto', (os.path.basename(file_path), open(file_path, 'rb'), 'image/png')))
        
        # 检查并打开报告文件
        if os.path.basename(file_path).endswith("pdf"):
            print(f"Files to be uploaded:: {file_path} ")
            files_list.append(('report', (os.path.basename(file_path), open(file_path, 'rb'), 'application/pdf')))
    
    # 构建POST数据字典
    data = {
        'idnumber': patient_id,  # 假设PatientID是身份证号
        'name': patient_name,
        'sex':  patient_sex,  # 如果性别的值未知，则使用空字符串
        'phone': patient_phone,
        'address': patient_address or '',  # 如果地址为空，则使用空字符串
        'device_code': device_code or '',  # 如果设备码为空，则使用空字符串
        'data_id': data_id,
        'title': report_title,
        'checkTime': study_date
    }

    print(data)
    # 鉴权
    authenticate_url = 'https://auth.lotusdata.com/v1/login/token'
    authentication_data = {
                            "username":"guokexiguang",
                            "password":"guokexiguang654321",
                            "usertype":"thirdparty",
                            "refreshtoken":"0"
                            }
    response = requests.post(authenticate_url, json=authentication_data)
    token = eval(response.text)["data"]

    headers = {
        "Authorization": f"JWT {token}"  
    }

    # 发送POST请求
    response = requests.post(api_url, files=files_list, data=data, headers=headers)
    if response.status_code == 200:
        print(f"Files uploaded successfully: {file_path} ")
    else:
        print(f"Failed to upload files: {file_path}, Status Code: {response.status_code}")

# 监控文件夹的事件处理器
class DrImageFolderHandler(FileSystemEventHandler):
    def __init__(self, root_folder, output_folder, api_url):
        self.root_folder = root_folder
        self.output_folder = output_folder
        self.api_url = api_url

        self.files_to_upload = []

        self.curr_file = ""

    #def on_created(self, event):
    def on_any_event(self, event):
        #if event.is_directory:
        if not(event.is_directory) and event.src_path.endswith(".pdf"):
            #print("event type is: " + event.event_type)
            if(("created" == event.event_type) and not(self.curr_file)):
                self.curr_file = event.src_path
                return
            elif(("modified" == event.event_type)):
                if(os.stat(event.src_path).st_size > 0 and (self.curr_file == event.src_path)):
                    self.curr_file = ""
                else:
                    return
            else:
                return
                            
            #new_folder = event.src_path
            new_folder = os.path.dirname(event.src_path)

            # 忽略 output_images 目录中的文件夹增加事件
            if "output_images" in new_folder:
                print(f"Ignoring folder creation in output directory: {new_folder}")
                return
            
            #print(f"New folder detected: {new_folder}")
            print("\n")
            print(f"New pdf file detected: {event.src_path}")
            print("file size: " + str(os.stat(event.src_path).st_size))
            output_folder = os.path.join(self.output_folder, os.path.basename(new_folder))
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
            files_to_process = []
            for filename in os.listdir(new_folder):
                if filename.endswith(".dcm") and not(filename.endswith("_pre.dcm")):
                    dicom_path = os.path.join(new_folder, filename)
                    png_filename, patient_name, study_date, patient_id, patient_sex, patient_phone, patient_address, device_code, data_id, report_title = process_dicom_file(dicom_path, output_folder)
                    files_to_process.append((png_filename, patient_name, study_date, patient_id, patient_sex, patient_phone, patient_address, device_code, data_id, report_title))
            
            files_to_process.append((event.src_path, patient_name, study_date, patient_id, patient_sex, patient_phone, patient_address, device_code, data_id, report_title))
            """"
            # 处理 report.rpt 文件
            rpt_path = os.path.join(new_folder, 'report.rpt')
            if os.path.exists(rpt_path):
                pdf_path = os.path.join(output_folder, 'report.pdf')
                convert_rpt_to_pdf(rpt_path, pdf_path)
                print(f"Report converted to PDF: {pdf_path}")
                # 将 PDF 文件信息添加到上传列表中
                files_to_process.append((pdf_path, patient_name, study_date, patient_id, patient_sex, patient_phone, patient_address, device_code, data_id, report_title))
            """           
            # 收集所有文件以待上传
            self.files_to_upload.extend(files_to_process)
            print(f"Files to upload: {len(self.files_to_upload)}")
            
            # 上传所有文件
            upload_files(self.files_to_upload, self.api_url)
            self.files_to_upload.clear()

# 主程序
if __name__ == "__main__":
    root_folder = "./"
    output_folder = "output_images"
    api_url = "https://iot.api.lotusdata.com/v1/signsdata/medicalreport"


    event_handler = DrImageFolderHandler(root_folder, output_folder, api_url)
    observer = Observer()
    observer.schedule(event_handler, root_folder, recursive=True)
    observer.start()
    print("Monitoring started...")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()
    observer.join()