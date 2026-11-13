from flask_login import UserMixin

class APILoginUser(UserMixin):
    def __init__(self, user_data):
        self.id = user_data.get("id")
        self.username = user_data.get("username")
        self.email = user_data.get("email")
        self.first_name = user_data.get("first_name")
        self.last_name = user_data.get("last_name")

    def get_id(self):
        return str(self.id)

    @property
    def is_authenticated(self):
        return True