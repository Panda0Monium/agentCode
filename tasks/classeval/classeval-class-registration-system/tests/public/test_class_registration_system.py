import unittest
from class_registration_system import ClassRegistrationSystem


class ClassRegistrationSystemTestRegisterStudent(unittest.TestCase):

    def setUp(self):
        self.registration_system = ClassRegistrationSystem()

    def test_register_student(self):
        student1 = {"name": "John", "major": "Computer Science"}
        self.assertEqual(self.registration_system.register_student(student1), 1)

    def test_register_student2(self):
        student1 = {"name": "John", "major": "Computer Science"}
        self.registration_system.register_student(student1)
        self.assertEqual(self.registration_system.register_student(student1), 0)

    def test_register_student3(self):
        student1 = {"name": "John", "major": "Computer Science"}
        student2 = {"name": "Alice", "major": "Mathematics"}
        self.assertEqual(self.registration_system.register_student(student1), 1)
        self.assertEqual(self.registration_system.register_student(student2), 1)
        self.assertEqual(self.registration_system.register_student(student2), 0)

class ClassRegistrationSystemTestRegisterClass(unittest.TestCase):

    def setUp(self):
        self.registration_system = ClassRegistrationSystem()

    def test_register_class(self):
        self.assertEqual(self.registration_system.register_class(student_name="John", class_name="CS101"), ["CS101"])

    def test_register_class2(self):
        self.registration_system.register_class(student_name="John", class_name="CS101")
        self.registration_system.register_class(student_name="John", class_name="CS102")
        self.assertEqual(self.registration_system.register_class(student_name="John", class_name="CS103"), ["CS101", "CS102", "CS103"])

    def test_register_class3(self):
        self.registration_system.register_class(student_name="John", class_name="CS101")
        self.registration_system.register_class(student_name="Tom", class_name="CS102")
        self.assertEqual(self.registration_system.register_class(student_name="John", class_name="CS103"), ["CS101", "CS103"])

class ClassRegistrationSystemTestGetStudent(unittest.TestCase):

    def setUp(self):
        self.registration_system = ClassRegistrationSystem()

    def test_get_students_by_major(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"}]

        cs_students = self.registration_system.get_students_by_major("Computer Science")

        self.assertEqual(cs_students, ["John", "Bob"])

    def test_get_students_by_major2(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"}]

        cs_students = self.registration_system.get_students_by_major("Computer Science")
        math_students = self.registration_system.get_students_by_major("Mathematics")

        self.assertEqual(cs_students, ["John", "Bob"])
        self.assertEqual(math_students, [])

    def test_get_students_by_major3(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"},
                                                {"name": "Alice", "major": "Mathematics"}]

        cs_students = self.registration_system.get_students_by_major("Computer Science")
        math_students = self.registration_system.get_students_by_major("Mathematics")

        self.assertEqual(cs_students, ["John", "Bob"])
        self.assertEqual(math_students, ["Alice"])

    def test_get_students_by_major4(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"},
                                             {"name": "Alice", "major": "Mathematics"},
                                             {"name": "Tom", "major": "Mathematics"},
                                             {"name": "Jerry", "major": "Mathematics"}]

        cs_students = self.registration_system.get_students_by_major("Computer Science")
        math_students = self.registration_system.get_students_by_major("Mathematics")
        self.assertEqual(cs_students, ["John", "Bob"])
        self.assertEqual(math_students, ["Alice", "Tom", "Jerry"])

class ClassRegistrationSystemTestGetMajor(unittest.TestCase):

    def setUp(self):
        self.registration_system = ClassRegistrationSystem()

    def test_get_all_major(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"}]

        majors = self.registration_system.get_all_major()

        self.assertEqual(majors, ["Computer Science"])

    def test_get_all_major2(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"},
                                             {"name": "Alice", "major": "Mathematics"}]

        majors = self.registration_system.get_all_major()

        self.assertEqual(majors, ["Computer Science", "Mathematics"])

    def test_get_all_major3(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"},
                                             {"name": "Alice", "major": "Mathematics"},
                                             {"name": "Tom", "major": "Mathematics"},
                                             {"name": "Jerry", "major": "Physics"}]

        majors = self.registration_system.get_all_major()

        self.assertEqual(majors, ["Computer Science", "Mathematics", "Physics"])

class ClassRegistrationSystemTestPopularClass(unittest.TestCase):

    def setUp(self):
        self.registration_system = ClassRegistrationSystem()

    def test_get_most_popular_class_in_major(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                             {"name": "Bob", "major": "Computer Science"},
                                             {"name": "Alice", "major": "Computer Science"}]

        self.registration_system.students_registration_classes = {"John": ["Algorithms", "Data Structures"],
                                            "Bob": ["Operating Systems", "Data Structures", "Algorithms"],
                                            "Alice": ["Data Structures", "Operating Systems", "Calculus"]}

        cs_most_popular_class = self.registration_system.get_most_popular_class_in_major("Computer Science")

        self.assertEqual(cs_most_popular_class, "Data Structures")

    def test_get_most_popular_class_in_major2(self):
        self.registration_system.students = [{"name": "John", "major": "Computer Science"},
                                                {"name": "Bob", "major": "Computer Science"},
                                                {"name": "Alice", "major": "Computer Science"},
                                                {"name": "Tom", "major": "Mathematics"},
                                                {"name": "Jerry", "major": "Mathematics"}]

        self.registration_system.students_registration_classes = {"John": ["Algorithms", "Data Structures"],
                                                                  "Bob": ["Data Structures", "Algorithms",
                                                                          "Operating Systems"],
                                                                  "Alice": ["Data Structures", "Operating Systems",
                                                                            "Calculus"],
                                                                    "Tom": ["Calculus", "Linear Algebra"],
                                                                    "Jerry": ["Linear Algebra", "Statistics"]}

        cs_most_popular_class = self.registration_system.get_most_popular_class_in_major("Computer Science")
        math_most_popular_class = self.registration_system.get_most_popular_class_in_major("Mathematics")
        self.assertEqual(cs_most_popular_class, "Data Structures")
        self.assertEqual(math_most_popular_class, "Linear Algebra")
