from .models import Dht11
from datetime import timedelta, datetime
from django.db import connection
from django.http import HttpResponse

from django.core.cache import cache
import requests
from django.db.models import Avg
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import DHT11serialize
from rest_framework.decorators import api_view
from rest_framework import status, generics
from rest_framework.response import Response
from django.conf import settings
import requests


def send_telegram_message(message):
    token = settings.TELEGRAM_BOT_AUTH_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    response = requests.post(url, data=payload)
    return response


@api_view(["POST"])
def dlist(request):
    if request.method == "POST":
        serial = DHT11serialize(data=request.data)
        print("temp is " + str(request.data.get("temp")))
        if request.data.get("temp") < 30:
            send_telegram_message(
                f"Hey there! The temperature in Oujda is currently {str(request.data.get('temp'))}°C. It's a bit chilly, so you might want to bundle up and wear something warm!"
            )
        elif request.data.get("temp") > 30:
            send_telegram_message(
                f"Warning! The temperature in Oujda is {str( request.data.get('temp'))}°C."
            )
        if serial.is_valid():
            serial.save()
            print("temp is " + str(request.data.get("temp")))
            print("saved!")
            return HttpResponse(serial.data, status=status.HTTP_201_CREATED)
        return HttpResponse(serial.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def getStatistics(request):
    # Check if data is cached
    cached_data = cache.get("statistics-summary")
    if cached_data:
        return Response({"data": cached_data})

    # Get the current date and time
    today = datetime.now().date()
    one_week_ago = today - timedelta(weeks=1)
    one_month_ago = today - timedelta(days=30)

    # TimescaleDB query for daily, weekly, and monthly statistics using time_bucket
    query = f"""
    WITH stats AS (
        SELECT
            time_bucket('1 day', dt) AS bucket_time,
            ROUND(AVG(temp),2) AS avg_temp,
            ROUND(AVG(hum),2) AS avg_hum
        FROM dht11
        WHERE dt >= '{one_month_ago}'
        GROUP BY bucket_time
    ),
    extremes AS (
        SELECT
            ROUND(MAX(temp),2) AS highest_temp,
            ROUND(MIN(temp),2) AS lowest_temp,
            ROUND(MAX(hum),2) AS highest_hum,
            ROUND(MIN(hum),2) AS lowest_hum
        FROM dht11
        WHERE dt >= '{one_month_ago}'
    )
    SELECT
        bucket_time,
        avg_temp,
        avg_hum,
        highest_temp,
        lowest_temp,
        highest_hum,
        lowest_hum
    FROM stats, extremes
    ORDER BY bucket_time DESC
    LIMIT 30;
    """

    # Execute the query
    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    # Initialize the data dictionary
    formatted_result = {
        "curr": {},
        "avg": {"daily": {}, "weekly": {}, "monthly": {}},
        "extremes": {
            "highest": {"temp": {}, "hum": {}},
            "lowest": {"temp": {}, "hum": {}},
        },
    }

    # Store the current record (latest data)
    current_record = Dht11.objects.order_by("-dt").first()
    curr = {
        "record": (
            DHT11serialize(current_record).data
            if current_record
            else {"temp": None, "hum": None, "dt": None}
        )
    }
    formatted_result["curr"] = curr

    # Growth Calculation Function
    def calculate_growth(current, previous):
        if current is not None and previous is not None and previous != 0:
            return ((current - previous) / previous) * 100
        return None

    # Initialize variables for previous averages
    prev_daily_avg = prev_weekly_avg = prev_monthly_avg = None

    # Process and format the results
    for row in result:
        # Format the averages for daily, weekly, and monthly
        formatted_result["avg"]["daily"] = {
            "record": {
                "temp": round(row[1], 2) if row[1] else None,
                "hum": round(row[2], 2) if row[2] else None,
                "dt": row[0].strftime("%Y-%m-%d"),
            },
            "humGrow": None,  # Will be calculated based on previous daily
            "humTemp": None,  # Will be calculated based on previous daily
        }

        formatted_result["extremes"]["highest"]["temp"] = (
            round(row[3], 2) if row[3] else None
        )
        formatted_result["extremes"]["highest"]["hum"] = (
            round(row[5], 2) if row[5] else None
        )
        formatted_result["extremes"]["lowest"]["temp"] = (
            round(row[4], 2) if row[4] else None
        )
        formatted_result["extremes"]["lowest"]["hum"] = (
            round(row[6], 2) if row[6] else None
        )

        # Store the daily averages for growth calculation
        prev_daily_avg = (row[1], row[2])

    # Additional queries for weekly and monthly averages (simplified for brevity)
    # The following should be executed with a separate query or added to the previous one
    weekly_avg = Dht11.objects.filter(dt__gte=one_week_ago).aggregate(
        avg_temp=Avg("temp"), avg_hum=Avg("hum")
    )
    monthly_avg = Dht11.objects.filter(dt__gte=one_month_ago).aggregate(
        avg_temp=Avg("temp"), avg_hum=Avg("hum")
    )

    # Weekly and Monthly Growth
    prev_weekly_avg = (
        (weekly_avg["avg_temp"], weekly_avg["avg_hum"]) if weekly_avg else (None, None)
    )
    prev_monthly_avg = (
        (monthly_avg["avg_temp"], monthly_avg["avg_hum"])
        if monthly_avg
        else (None, None)
    )

    # Calculate growths for daily, weekly, and monthly
    daily_hum_growth = calculate_growth(
        formatted_result["avg"]["daily"]["record"]["hum"], prev_daily_avg[1]
    )
    daily_temp_growth = calculate_growth(
        formatted_result["avg"]["daily"]["record"]["temp"], prev_daily_avg[0]
    )

    weekly_hum_growth = calculate_growth(weekly_avg["avg_hum"], prev_weekly_avg[1])
    weekly_temp_growth = calculate_growth(weekly_avg["avg_temp"], prev_weekly_avg[0])

    monthly_hum_growth = calculate_growth(monthly_avg["avg_hum"], prev_monthly_avg[1])
    monthly_temp_growth = calculate_growth(monthly_avg["avg_temp"], prev_monthly_avg[0])

    # Update the growth fields in formatted_result
    formatted_result["avg"]["daily"]["humGrow"] = daily_hum_growth
    formatted_result["avg"]["daily"]["humTemp"] = daily_temp_growth

    formatted_result["avg"]["weekly"] = {
        "record": {
            "temp": round(weekly_avg["avg_temp"] or 0, 2),
            "hum": round(weekly_avg["avg_hum"] or 0, 2),
            "dt": one_week_ago.isoformat(),
        },
        "humGrow": weekly_hum_growth,
        "humTemp": weekly_temp_growth,
    }

    formatted_result["avg"]["monthly"] = {
        "record": {
            "temp": round(monthly_avg["avg_temp"] or 0, 2),
            "hum": round(monthly_avg["avg_hum"] or 0, 2),
            "dt": one_month_ago.isoformat(),
        },
        "humGrow": monthly_hum_growth,
        "humTemp": monthly_temp_growth,
    }

    # Cache the result for later requests
    cache.set("statistics-summary", formatted_result, 30)  # Cache for 30 seconds

    return Response({"data": formatted_result})


@api_view(["GET"])
def getMonthsAverage(request):
    n_months = int(request.GET.get("n", 6))
    if n_months > 24:  # Optional limit on months
        n_months = 24

    # Get the current date
    today = datetime.now().date()

    # Calculate the first day of the first month in the range
    first_day_of_current_month = today.replace(day=1)
    first_day_of_n_months_ago = (
        first_day_of_current_month - timedelta(days=n_months * 30)
    ).replace(day=1)

    # Query to generate a series of months and aggregate the data by month
    query = f"""
    WITH month_range AS (
        SELECT generate_series(
            '{first_day_of_n_months_ago}'::date,
            '{today}'::date,
            '1 month'::interval
        )::date AS bucket_month
    )
    SELECT
        mr.bucket_month,
        ROUND(AVG(dht.temp),2) AS temp,
        ROUND(AVG(dht.hum),2) AS hum
    FROM month_range mr
    LEFT JOIN dht11 dht ON date_trunc('month', dht.dt) = mr.bucket_month
    GROUP BY mr.bucket_month
    ORDER BY mr.bucket_month DESC
    LIMIT {n_months};
    """

    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    # Format the result into a list of dictionaries with appropriate keys
    formatted_result = [
        {"dt": row[0].strftime("%Y-%m"), "temp": row[1], "hum": row[2]}
        for row in result
    ]

    return Response({"data": formatted_result})


@api_view(["GET"])
def getRangeAverage(request):
    from_date = request.GET.get("from")
    to_date = request.GET.get("to")

    # Validate and parse the input dates
    try:
        from_date = datetime.fromisoformat(from_date).date()
        to_date = datetime.fromisoformat(to_date).date()
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid date format. Use ISO format (YYYY-MM-DD)."}, status=400
        )

    if from_date > to_date:
        return Response(
            {"error": "from_date must be earlier than or equal to to_date."}, status=400
        )

    # TimescaleDB query to generate the series and fill missing days with null values for temp and hum
    query = f"""
    WITH day_range AS (
        SELECT generate_series(
            '{from_date}'::date,
            '{to_date}'::date,
            '1 day'::interval
        )::date AS bucket_day
    )
    SELECT
        dr.bucket_day,
        ROUND(AVG(dht.temp), 2) AS temp,
        ROUND(AVG(dht.hum), 2) AS hum
    FROM
        day_range dr
    LEFT JOIN dht11 dht ON dht.dt::date = dr.bucket_day
    GROUP BY
        dr.bucket_day
    ORDER BY
        dr.bucket_day ASC;
    """

    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    if not result:
        # Handle empty result
        return Response({"data": [], "message": "No data found for the given range."})

    # Format the result into a list of dictionaries
    formatted_result = [
        {
            "dt": row[0].strftime("%Y-%m-%d"),
            "temp": row[1] if row[1] is not None else None,
            "hum": row[2] if row[2] is not None else None,
        }
        for row in result
    ]
    formatted_result.reverse()
    return Response({"data": formatted_result})


@api_view(["GET"])
def getDailyAverage(request):
    n_days = int(request.GET.get("n", 7))
    if n_days > 800:
        n_days = 800

    # Get the current date
    today = datetime.now().date()

    # Generate the date range for the past `n_days`
    start_date = today - timedelta(days=n_days)

    query = f"""
    WITH date_range AS (
        SELECT generate_series(
            '{start_date}'::date,
            '{today}'::date,
            '1 day'::interval
        )::date AS bucket_time
    )
    SELECT
        dr.bucket_time,
        ROUND(AVG(dht.temp),2) AS temp,
        ROUND(AVG(dht.hum),2) AS hum
    FROM date_range dr
    LEFT JOIN dht11 dht ON time_bucket('1 day', dht.dt) = dr.bucket_time
    GROUP BY dr.bucket_time
    ORDER BY dr.bucket_time DESC
    LIMIT {n_days};
    """

    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    formatted_result = [{"dt": row[0], "temp": row[1], "hum": row[2]} for row in result]

    return Response({"data": formatted_result})


@api_view(["GET"])
def getDateDifference(request):
    from_date = request.GET.get("from")
    to_date = request.GET.get("to")

    # Validate and parse the input dates
    try:
        from_date = datetime.fromisoformat(from_date).date()
        to_date = datetime.fromisoformat(to_date).date()
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid date format. Use ISO format (YYYY-MM-DD)."}, status=400
        )

    if from_date > to_date:
        return Response(
            {"error": "from_date must be earlier than or equal to to_date."}, status=400
        )

    # TimescaleDB query using direct comparison of the two dates
    query = f"""
    WITH data_from_dates AS (
        -- Fetch data for the first date
        SELECT
            dht.dt::date AS date,
            ROUND(AVG(dht.temp), 2) AS temp,
            ROUND(AVG(dht.hum), 2) AS hum
        FROM
            dht11 dht
        WHERE
            dht.dt::date = '{from_date}'
        GROUP BY
            dht.dt::date
        UNION ALL
        -- Fetch data for the second date
        SELECT
            dht.dt::date AS date,
            ROUND(AVG(dht.temp), 2) AS temp,
            ROUND(AVG(dht.hum), 2) AS hum
        FROM
            dht11 dht
        WHERE
            dht.dt::date = '{to_date}'
        GROUP BY
            dht.dt::date
    )
    SELECT
        -- Select the data for both dates
        date,
        temp,
        hum
    FROM data_from_dates
    ORDER BY date;
    """

    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchall()

    if len(result) < 2:
        return Response({"error": "Data not found for both dates."}, status=404)

    # Extract data for both dates
    from_temp, from_hum = result[0][1], result[0][2]
    to_temp, to_hum = result[1][1], result[1][2]

    # Calculate the differences between the two dates
    temp_diff = (
        to_temp - from_temp if to_temp is not None and from_temp is not None else None
    )
    hum_diff = (
        to_hum - from_hum if to_hum is not None and from_hum is not None else None
    )

    # Prepare and return the response
    data = {
        "from_date": from_date,
        "to_date": to_date,
        "temp_diff": temp_diff,
        "hum_diff": hum_diff,
    }

    return Response({"data": data})


class Dhtviews(generics.CreateAPIView):
    queryset = Dht11.objects.all()
    serializer_class = DHT11serialize
