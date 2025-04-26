import os

from flask_wtf import CSRFProtect
from app import create_app

app = create_app(os.getenv('FLASK_ENV', 'default'))
csrf = CSRFProtect(app)

if __name__ == '__main__':
    app.run(debug=(os.getenv('FLASK_ENV') == 'development'), host='0.0.0.0')
