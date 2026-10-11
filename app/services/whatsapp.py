import requests
from requests import RequestException
from fastapi import HTTPException

from app.config.settings import settings

GRAPH_URL_TEMPLATE = "https://graph.facebook.com/v18.0/{phone_number_id}/messages"


class WhatsAppService:
    @staticmethod
    def send_text_message(phone: str, body: str):
        url = GRAPH_URL_TEMPLATE.format(phone_number_id=settings.PHONE_NUMBER_ID)
        headers = {
            "Authorization": f"Bearer {settings.ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": body},
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        except RequestException as exc:
            raise HTTPException(status_code=503, detail=f"WhatsApp API unreachable: {exc}")

        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        data = resp.json()
        if data.get("error"):
            raise HTTPException(status_code=500, detail=data["error"])
        return data
