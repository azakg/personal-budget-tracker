"""Receipt upload and processing routes."""
import os
import uuid
from datetime import datetime
from flask import jsonify, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.receipts import bp
from app.database import get_db_connection
from app.utils.helpers import allowed_file
from app.services.receipt_parser import ReceiptParser


@bp.route("/upload", methods=["POST"])
@login_required
def upload_receipt():
    """Upload and process receipt image.

    Returns:
        JSON response with parsed transaction data or error
    """
    # Validate file presence
    if "receipt" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["receipt"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Validate file type
    if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
        return jsonify({
            "error": f"Invalid file type. Allowed: {', '.join(current_app.config['ALLOWED_EXTENSIONS'])}"
        }), 400

    # Check file size (if provided)
    if request.content_length and request.content_length > current_app.config['MAX_FILE_SIZE']:
        return jsonify({
            "error": f"File too large. Maximum size: {current_app.config['MAX_FILE_SIZE'] / 1024 / 1024:.1f}MB"
        }), 413

    # Save file with secure filename
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{original_filename}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)

    try:
        file.save(filepath)
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {str(e)}"}), 500

    # Parse receipt
    try:
        parser = ReceiptParser(
            openai_api_key=current_app.config['OPENAI_API_KEY'],
            aws_region=current_app.config['AWS_REGION']
        )
        parsed_data = parser.parse_receipt(filepath)
    except Exception as e:
        print(f"Receipt parsing error: {e}")
        return jsonify({
            "error": "Failed to parse receipt",
            "details": str(e)
        }), 500

    # Insert transaction into database
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO transactions (user_id, tx_date, kind, category, amount, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    current_user.id,
                    parsed_data["date"],
                    "expense",
                    parsed_data["category"],
                    parsed_data["amount"],
                    parsed_data["note"],
                    datetime.utcnow().isoformat(),
                ),
            )
        print("Transaction inserted successfully into DB")
        inserted = True
    except Exception as e:
        print(f"DB insert error: {e}")
        inserted = False

    # Return response
    if inserted:
        return jsonify({
            "message": "Receipt uploaded and transaction added automatically",
            "path": filepath,
            "extracted_text": parsed_data["raw_text"][:500],  # First 500 chars
            "ai_parsed": {
                "date": parsed_data["date"],
                "category": parsed_data["category"],
                "amount": parsed_data["amount"],
                "note": parsed_data["note"]
            }
        }), 200
    else:
        return jsonify({
            "message": "Receipt uploaded but failed to add transaction",
            "path": filepath,
            "extracted_text": parsed_data["raw_text"][:500],
            "error": "Database insert failed; see server logs"
        }), 500
