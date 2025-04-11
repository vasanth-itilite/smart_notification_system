import jwt
import requests

def send_notification(data, username):
    # url = "https://ilmobilestreamapi.iltech.in/service/notification"
    url = "https://ilqamobilestreamapi.iltech.in/service/notification"

    template_data ={
        "user": [
            username
        ],
        "body": data["notification"],
        "title": data["title"],
        "tripId": data["trip_id"],
        "action": "SmartNotification",
        "navigation": {
            "legRequestId": data["leg_request_id"],
            "tripId": data["trip_id"],
            "emailId": username,
        }
    }

    token = jwt.encode(template_data, "itiliteNotification", algorithm="HS256")

    headers = {
        "Content-Type": "application/json",
        "device-fingerprint": "93A313C5-AED2-4A1D-A559-E15CB8AA7399",
        "access-token": token
    }

    response = requests.post(url, json=template_data, headers=headers)
    try:
        print("✅ Notification sent:", response.json())
    except Exception:
        print("✅ Status code:", response.status_code)
        print("✅ Headers:", response.headers)
        print("✅ Body:", response.text or "<empty>")


if __name__ == "__main__":
    username = "dashboarduser@yopmail.com"  # 📩 User who gets the notification

    data = {
        "trip_id": "0555-0809",  # 🧳✈️ Trip reference
        "notification": "🚀 Wanna see what All In With 7-2 built? 🤯",
        "title": "🎉 Hooray Hackathon at Itilite 🧠💻",
        "leg_request_id": "67d7bcf1040e1c2bba70080e",  # 🔢 Leg request ID
        "action": "SmartNotification",  # 🧠🔔 Notification type
    }

    send_notification(data=data, username=username)  # 📬 Send it!
