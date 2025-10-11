import json
import os
import tkinter as tk
from tkinter import messagebox, simpledialog

class EducationSystem:
    def __init__(self, filename='education_data.json'):
        self.filename = filename
        self.data = {'students': [], 'teachers': [], 'courses': []}
        self.load_data()

    def load_data(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as file:
                self.data = json.load(file)

    def save_data(self):
        with open(self.filename, 'w') as file:
            json.dump(self.data, file, indent=4)

    def add_student(self, name, student_id):
        self.data['students'].append({"name": name, "student_id": student_id})
        self.save_data()

    def add_teacher(self, name, teacher_id):
        self.data['teachers'].append({"name": name, "teacher_id": teacher_id})
        self.save_data()

    def add_course(self, name, course_code):
        self.data['courses'].append({"name": name, "course_code": course_code})
        self.save_data()

    def get_all(self, category):
        return self.data.get(category, [])

class EducationApp:
    def __init__(self, root, system):
        self.system = system
        self.root = root
        self.root.title("Education System")

        tk.Button(root, text="Add Student", width=20, command=self.add_student).pack(pady=5)
        tk.Button(root, text="View All Students", width=20, command=self.view_students).pack(pady=5)
        tk.Button(root, text="Add Teacher", width=20, command=self.add_teacher).pack(pady=5)
        tk.Button(root, text="View All Teachers", width=20, command=self.view_teachers).pack(pady=5)
        tk.Button(root, text="Add Course", width=20, command=self.add_course).pack(pady=5)
        tk.Button(root, text="View All Courses", width=20, command=self.view_courses).pack(pady=5)
        tk.Button(root, text="Exit", width=20, command=root.quit).pack(pady=5)

    def add_student(self):
        name = simpledialog.askstring("Input", "Enter Student Name:")
        student_id = simpledialog.askstring("Input", "Enter Student ID:")
        if name and student_id:
            self.system.add_student(name, student_id)
            messagebox.showinfo("Success", "Student added successfully!")

    def view_students(self):
        students = self.system.get_all('students')
        self.show_list("Students", students)

    def add_teacher(self):
        name = simpledialog.askstring("Input", "Enter Teacher Name:")
        teacher_id = simpledialog.askstring("Input", "Enter Teacher ID:")
        if name and teacher_id:
            self.system.add_teacher(name, teacher_id)
            messagebox.showinfo("Success", "Teacher added successfully!")

    def view_teachers(self):
        teachers = self.system.get_all('teachers')
        self.show_list("Teachers", teachers)

    def add_course(self):
        name = simpledialog.askstring("Input", "Enter Course Name:")
        course_code = simpledialog.askstring("Input", "Enter Course Code:")
        if name and course_code:
            self.system.add_course(name, course_code)
            messagebox.showinfo("Success", "Course added successfully!")

    def view_courses(self):
        courses = self.system.get_all('courses')
        self.show_list("Courses", courses)

    def show_list(self, title, items):
        if not items:
            messagebox.showinfo(title, "No records found.")
            return
        result = "\n".join([str(item) for item in items])
        messagebox.showinfo(title, result)

if __name__ == "__main__":
    root = tk.Tk()
    app = EducationApp(root, EducationSystem())
    root.mainloop()
