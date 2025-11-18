"""Receipt upload and processing blueprint."""
from flask import Blueprint

bp = Blueprint('receipts', __name__, url_prefix='/receipts')

from app.receipts import routes
