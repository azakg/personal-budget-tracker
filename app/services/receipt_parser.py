"""Receipt parsing service using AWS Textract and OpenAI."""
import re
import json
from datetime import date
from typing import Dict, Optional

import boto3
from openai import OpenAI

from app.utils.helpers import to_amount, to_iso_date


class ReceiptParser:
    """Service for parsing receipts using AWS Textract and OpenAI."""

    def __init__(self, openai_api_key: str, aws_region: str = "us-east-1"):
        """Initialize parser with API credentials.

        Args:
            openai_api_key: OpenAI API key
            aws_region: AWS region for Textract
        """
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.textract_client = boto3.client("textract", region_name=aws_region)

    def extract_text_from_image(self, filepath: str) -> str:
        """Extract text from receipt image using AWS Textract.

        Args:
            filepath: Path to receipt image

        Returns:
            Extracted text from receipt

        Raises:
            Exception: If Textract API call fails
        """
        with open(filepath, "rb") as img_file:
            bytes_data = img_file.read()

        response = self.textract_client.detect_document_text(
            Document={"Bytes": bytes_data}
        )

        extracted_text = "\n".join(
            block.get("DetectedText") or block.get("Text", "")
            for block in response.get("Blocks", [])
            if block.get("BlockType") == "LINE"
        )

        return extracted_text

    def parse_with_ai(self, extracted_text: str) -> Dict[str, any]:
        """Parse extracted text using OpenAI to extract transaction details.

        Args:
            extracted_text: Text extracted from receipt

        Returns:
            Dictionary with keys: category, amount, note, date
        """
        prompt = f"""
        You are an assistant that reads receipts and extracts transaction details.
        Return ONLY JSON with keys: category (one of Grocery, Car, Utilities, Apartment Rent, Entertainment, Health, Other),
        amount (number), note (short), date (YYYY-MM-DD). If unsure use 'Other' for category.
        Receipt:
        ---
        {extracted_text}
        ---
        """

        try:
            completion = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a precise financial extraction AI agent."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            ai_resp = completion.choices[0].message.content
            parsed = json.loads(ai_resp or "{}")
            return parsed
        except Exception as e:
            print(f"OpenAI parsing error: {e}")
            return {}

    def apply_heuristics(self, category: str, amount: float, extracted_text: str) -> tuple[str, float]:
        """Apply heuristic rules to improve category and amount detection.

        Args:
            category: Category from AI parsing
            amount: Amount from AI parsing
            extracted_text: Raw extracted text

        Returns:
            Tuple of (improved_category, improved_amount)
        """
        low = extracted_text.lower()

        # Try to find amount if AI didn't find one
        if amount == 0.0:
            m = re.findall(r'\$?\s?(\d+\.\d{2})', extracted_text.replace(",", ""))
            if m:
                amount = float(m[-1])  # Use last one (usually total)

        # Improve category detection if AI returned "Other"
        if category == "Other":
            if any(word in low for word in ["gallon", "gas", "fuel", "pump"]):
                category = "Car"
            elif any(word in low for word in ["costco", "walmart", "kroger", "aldi"]):
                category = "Grocery"
            elif any(word in low for word in ["netflix", "cinema", "movie", "theater"]):
                category = "Entertainment"

        return category, amount

    def parse_receipt(self, filepath: str) -> Dict[str, any]:
        """Parse receipt and extract transaction data.

        Args:
            filepath: Path to receipt image

        Returns:
            Dictionary with parsed transaction data:
                - date: ISO format date
                - category: Transaction category
                - amount: Transaction amount
                - note: Transaction note
                - raw_text: Original extracted text
        """
        # Step 1: Extract text using Textract
        extracted_text = self.extract_text_from_image(filepath)
        print(f"Textract extracted text (first 500 chars):\n{extracted_text[:500]}")

        # Step 2: Parse with OpenAI
        ai_parsed = self.parse_with_ai(extracted_text)
        print(f"OpenAI parsed data: {ai_parsed}")

        # Step 3: Normalize data
        tx_date = to_iso_date(ai_parsed.get("date", ""), date.today().isoformat())
        category = (ai_parsed.get("category") or "Other").strip() or "Other"
        note = (ai_parsed.get("note") or "AI-generated transaction").strip()
        amount = to_amount(ai_parsed.get("amount"))

        # Step 4: Apply heuristics
        category, amount = self.apply_heuristics(category, amount, extracted_text)

        return {
            "date": tx_date,
            "category": category,
            "amount": amount,
            "note": note,
            "raw_text": extracted_text
        }
