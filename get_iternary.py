import requests
from datetime import datetime, timedelta, timezone
def generate_flight_notifications():
    url = 'https://itilite-stream-qa-1.iltech.in/api/v1/traveler/dashboard/business/itinerary/upcoming'
    params = {
        'page_no': 1,
        'limit': 10,
        'sort': 'journey:asc'  # '%3A' = ':'
    }
    headers = {
        'accept': '*/*',
        'accept-language': 'en-GB,en;q=0.9',
        'cache-control': 'no-cache',
        'client-id': '555',
        'origin': 'https://qatravelapp.iltech.in',
        'pragma': 'no-cache',
        'role': 'traveler',
        'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'authorization': f'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzQ0Mzk4MjEzLCJqdGkiOiJmNzNkMWNjYzk4YmI0ODI4YjZmMGVmMWM4NGM5N2VmZCIsInVzZXJfaWQiOiJkYXNoYm9hcmR1c2VyQHlvcG1haWwuY29tIn0.U1ihaJhRdb9qAnrHURULvdJZt9DJR0D1oMWzxE_-oobOSuTyQ8JJf6NzbkSZLvPt7H9mgnIB4pcMp2f92UyuPpFHG2VCrRCSMizxtYnA73f-2P4bjn4NsufDvXD1PL2bQQWufDlp7o2DXARXq9yItko2rdXhvd3SI-8yn3KnobDu0N2X9jyEDjIBHymGBbS59hEmLNXYzRcGa3CNWpmH2OKZGOOrJokwglFau3OdT1S3juqZlgdJYyy2EDGsNn7PWU_Uw95aA3BycTlZG6qbPBoKxkXKel80USmeJzF7u3LxWlecrAfrsGtzENNp2x_gJPAuax4CB9DuJ4gU731au7U9YlAOAYQy9aqQRjz-o_rHCxErDi0K3MTi1n132eVxD7euE0H-guq8l4tofNgru0l8eHb8UV7WVqOFTgq3b_MRfbVJIMJ5sEUqNRJAyYcOqYdRFl0cVxwhigMt3ZjY1ScFAYMOFmBgYyixzTTc2dhASYKsn4NDEhx-8hXf7-H9xpomRTGqqQgUpzbaXXfa9zyS88vySQID7aftaHz0EjgivJ1WWYSq8RaWZ3zeIdemCu74aSnBKtb0mavPBd8P8rC-dhlWNHz9WB-Cm61dkUuMycwabwbUm_rpeoU6v4Lz4FISTUbJgqiVMstGFP08Hes9r8FsQ8inCyHj5xIj8ho'
    }

    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    print(f"Response: {data}")
    now = datetime.now(timezone.utc)
    final_data_to_share = {"pre_info": {}, "current_info": {}, "post_info": {}}
    for each in data["data"]:
        initial_trip_details = each['trip_details']
        trip_id = initial_trip_details['trip_id']
        min_date_str = each['trip_details']['min_date_utc']
        max_date_str = each['trip_details']['max_date_utc']
        min_date = datetime.fromisoformat(min_date_str) if min_date_str else None
        max_date = datetime.fromisoformat(max_date_str) if max_date_str else None
        print(f"Processing trip {trip_id} -  {now} vs {min_date} - {max_date}")
        # Apply the filter logic
        if not min_date or not max_date:
            print(f"Ignoring trip {trip_id} due to date filter")
            continue

        if min_date and min_date > now + timedelta(days=15):
            print(f"Ignoring trip {trip_id} as min date is in the future")
            continue
        if max_date and max_date < now - timedelta(days=2):
            print(f"Ignoring trip {trip_id} as max date is in the past")
            continue
        url_for_trip_details = f'https://itilite-stream-qa-1.iltech.in/api/v1/dashboard/itinerary/{trip_id}'
        response_trip_details = requests.get(url_for_trip_details, headers=headers)
        trip_details = response_trip_details.json()
        basic_info = {
            "trip_id": trip_id,
            "client_id": initial_trip_details["client_id"],
            "trip_title": initial_trip_details.get("title", {}).get("default", "")
        }
        formatted_data = {}
        for each_traveller in trip_details['data']['travellers']:
            current_pax_info = {
                "full_name": each_traveller.get("first_name", "") + each_traveller.get("last_name", ""),
                "email": each_traveller.get("email", "")
            }
            formatted_data[each_traveller["pax_id"]] = current_pax_info

        if trip_details['data'].get('flights', {}):
            flights_info = trip_details['data'].get('flights', {})
            for each_flight_info in flights_info.get("legs", []):
                try:
                    pax_wise_leg_info = {}
                    leg_request_id = each_flight_info.get("leg_request_id", "")
                    pnr = each_flight_info.get("pnr", "")
                    booking_id = each_flight_info.get("booking_id", "")
                    pre = False
                    current = False
                    post = False
                    departure_time = each_flight_info.get("from", {}).get('departure_datetime', '')
                    arrival_time = each_flight_info.get("to", {}).get('arrival_datetime', '')
                    if not departure_time or not arrival_time:
                        print(f"Ignoring flight leg in trip {trip_id} as departure or arrival time is missing")
                        continue
                    departure_time = datetime.fromisoformat(departure_time)
                    arrival_time = datetime.fromisoformat(arrival_time)
                    print(f" Departure Time: {departure_time}, Arrival Time: {arrival_time}, now : {now}")
                    if now + timedelta(days=5) < departure_time < now + timedelta(days=8):
                        pre = True
                        for index, each_segment in enumerate(each_flight_info.get("segments", [])):
                            for each_pax_details in each_segment.get("pax_details", []):
                                if each_pax_details.get("status", "") == "booked" or each_pax_details.get("status",
                                                                                                          "") == "confirmed":
                                    if each_pax_details.get("pax_id", ""):
                                        pax_id = each_pax_details.get("pax_id", "")
                                        if pax_id not in pax_wise_leg_info:
                                            pax_wise_leg_info.update({pax_id: []})
                                        pax_wise_leg_info[pax_id].append(each_segment)
                    elif now < departure_time < now + timedelta(days=5):
                        current = True
                        for index, each_segment in enumerate(each_flight_info.get("segments", [])):
                            for each_pax_details in each_segment.get("pax_details", []):
                                if each_pax_details.get("status", "") == "booked" or each_pax_details.get("status",
                                                                                                          "") == "confirmed":
                                    pax_id = each_pax_details.get("pax_id", "")
                                    if pax_id not in pax_wise_leg_info:
                                        pax_wise_leg_info.update({pax_id: []})
                                    pax_wise_leg_info[pax_id].append(each_segment)
                    elif now < arrival_time < now + timedelta(days=30):
                        post = True
                        for index, each_segment in enumerate(each_flight_info.get("segments", [])):
                            for each_pax_details in each_segment.get("pax_details", []):
                                if each_pax_details.get("status", "") == "booked" or each_pax_details.get("status",
                                                                                                          "") == "confirmed":
                                    pax_id = each_pax_details.get("pax_id", "")
                                    if pax_id not in pax_wise_leg_info:
                                        pax_wise_leg_info.update({pax_id: []})
                                    pax_wise_leg_info[pax_id].append(each_segment)
                    for each_pax_id, each_segment_list in pax_wise_leg_info.items():
                        leg_info = {}
                        leg_info.update({"leg_request_id": leg_request_id})
                        leg_info.update({"pnr": pnr})
                        leg_info.update({"booking_id": booking_id})
                        leg_info.update({"trip_id": trip_id})
                        leg_info.update({"pax_info": formatted_data.get(each_pax_id, {})})
                        leg_info.update(
                            {"departure_time": each_segment_list[0].get("from", {}).get("departure_datetime", "")})
                        leg_info.update(
                            {"arrival_time": each_segment_list[-1].get("to", {}).get("arrival_datetime", "")})
                        leg_info.update(
                            {"departure_airport_name": each_segment_list[0].get("from", {}).get("airport_name", "")})
                        leg_info.update(
                            {"arrival_airport_name": each_segment_list[-1].get("to", {}).get("airport_name", "")})
                        leg_info.update(
                            {"departure_airport_code": each_segment_list[0].get("from", {}).get("iata", "")})
                        leg_info.update({"arrival_airport_code": each_segment_list[-1].get("to", {}).get("iata", "")})
                        leg_info.update({"departure_city": each_segment_list[0].get("from", {}).get("city", "")})
                        leg_info.update({"arrival_city": each_segment_list[-1].get("to", {}).get("city", "")})
                        leg_info.update({"segment": each_segment_list})
                        leg_info.update({"title": "Flight"})
                        leg_info.update({"mode": "flight"})
                        if pre:
                            final_data_to_share["pre_info"].setdefault(each_pax_id, []).append(leg_info)
                        elif current:
                            final_data_to_share["current_info"].setdefault(each_pax_id, []).append(leg_info)
                        elif post:
                            final_data_to_share["post_info"].setdefault(each_pax_id, []).append(leg_info)
                except Exception as ex:
                    print(f"Error occurred while processing flight leg: {ex}")
                    continue

        for each_hotel_info in trip_details['data'].get('hotels', {}).get("legs", []):
            try:
                leg_request_id = each_hotel_info.get("leg_request_id", "")
                check_in_time = each_hotel_info.get("hotel_details", {}).get("check_in_datetime", "")
                check_out_time = each_hotel_info.get("hotel_details", {}).get("check_out_datetime", "")
                if not check_in_time or not check_out_time:
                    print(f"Ignoring hotel leg in trip {trip_id} as check in or check out time is missing")
                    continue
                check_in_time = datetime.fromisoformat(check_in_time)
                check_out_time = datetime.fromisoformat(check_out_time)
                pax_ids = set()
                pre = False
                post = False
                current = False

                print(f" Check in Time: {check_in_time}, Check out Time: {check_out_time}, now : {now}")
                if now + timedelta(days=5) < check_in_time < now + timedelta(days=8):
                    pre = True
                    for each_room in each_hotel_info.get("room_details", []):
                        for each_pax_details in each_room.get("pax_details", []):
                            if each_pax_details.get("status", "") == "confirmed" or each_pax_details.get("status",
                                                                                                         "") == "booked":
                                pax_id = each_pax_details.get("pax_id", "")
                                if pax_id:
                                    pax_ids.add(pax_id)

                elif now < check_in_time < now + timedelta(days=5):
                    current = True
                    for each_room in each_hotel_info.get("room_details", []):
                        for each_pax_details in each_room.get("pax_details", []):
                            if each_pax_details.get("status", "") == "confirmed" or each_pax_details.get("status",
                                                                                                         "") == "booked":
                                pax_id = each_pax_details.get("pax_id", "")
                                if pax_id:
                                    pax_ids.add(pax_id)

                elif now < check_out_time < now + timedelta(days=30):
                    post = True
                    for each_room in each_hotel_info.get("room_details", []):
                        for each_pax_details in each_room.get("pax_details", []):
                            if each_pax_details.get("status", "") == "confirmed" or each_pax_details.get("status",
                                                                                                         "") == "booked":
                                pax_id = each_pax_details.get("pax_id", "")
                                if pax_id:
                                    pax_ids.add(pax_id)
                for each_pax_id in pax_ids:
                    leg_info = {}
                    leg_info.update({"leg_request_id": leg_request_id})
                    leg_info.update({"trip_id": trip_id})
                    leg_info.update({"mode": "hotel"})
                    leg_info.update({"pax_info": formatted_data.get(each_pax_id, {})})
                    leg_info.update({"check_in_time": check_in_time})
                    leg_info.update({"check_out_time": check_out_time})
                    leg_info.update({"hotel_name": each_hotel_info.get("hotel_details", {}).get("name", "")})
                    leg_info.update({"hotel_address": each_hotel_info.get("hotel_details", {}).get("address", {})})
                    leg_info.update({"hotel_details": each_hotel_info.get("hotel_details", {})})
                    leg_info.update({"booking_id": each_hotel_info.get("booking_id", "")})
                    if pre:
                        final_data_to_share["pre_info"].setdefault(each_pax_id, []).append(leg_info)
                    elif current:
                        final_data_to_share["current_info"].setdefault(each_pax_id, []).append(leg_info)
                    elif post:
                        final_data_to_share["post_info"].setdefault(each_pax_id, []).append(leg_info)
            except Exception as ex:
                print(f"Error occurred while processing hotel leg: {ex}")
                continue

    return final_data_to_share

