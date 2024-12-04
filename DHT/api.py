from .models import Dht11
from datetime import timedelta
import asyncio
from django.core.cache import cache
from django.db.models import Avg
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone
from django.utils.timezone import now
from .serializers import DHT11serialize
from rest_framework.decorators import api_view
from rest_framework import status, generics
from rest_framework.response import Response
from telegram import Bot
from django.conf import settings





def send_telegram_message(body):
    async def send_message():
        bot = Bot(token=settings.TELEGRAM_BOT_AUTH_TOKEN)            
        chat_id = settings.TELEGRAM_CHAT_ID      
        await bot.send_message(chat_id=chat_id, text=body)
    asyncio.run(send_message())    





@api_view(["GET", "POST"])
def dlist(request):
    if request.method == "GET":
        all_data = Dht11.objects.all().order_by("dt")
        data_ser = DHT11serialize(all_data, many=True)
        return Response({"data": data_ser.data})
    elif request.method == "POST":
        
        serial = DHT11serialize(data=request.data)
        if request.data.temp < 30:
            send_telegram_message(f"Warning! the temperature in oujda is {request.data.temp} Celiceis, consider wearing warmth cloths.")        
        elif request.data.temp > 30:
            send_telegram_message(f"Warning! the temperature in oujda is {request.data.temp} Celiceis.")                        
        if serial.is_valid():
            serial.save()
            return Response(serial.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serial.errors, status=status.HTTP_400_BAD_REQUEST)



@api_view(["GET"])
def getStatistics(request):
    # Get the current date and time
    cashedData = cache.get("statistics-summary")
    if not cashedData:
        today = now()
        one_week_ago = today - timedelta(weeks=1)
        one_month_ago = today - timedelta(days=30)

        # Time ranges for comparison
        yesterday = today - timedelta(days=1)
        last_week_start = one_week_ago - timedelta(weeks=1)
        last_month_start = one_month_ago - timedelta(days=30)

        # Current Record
        current_record = Dht11.objects.order_by("-dt").first()
        curr = {
            "record": (
                DHT11serialize(current_record).data
                if current_record
                else {"temp": None, "hum": None, "dt": None}
            )
        }

        daily_avg = Dht11.objects.filter(dt__date=today.date()).aggregate(
            avg_temp=Avg("temp"), avg_hum=Avg("hum")
        )
        weekly_avg = Dht11.objects.filter(dt__gte=one_week_ago).aggregate(
            avg_temp=Avg("temp"), avg_hum=Avg("hum")
        )
        monthly_avg = Dht11.objects.filter(dt__gte=one_month_ago).aggregate(
            avg_temp=Avg("temp"), avg_hum=Avg("hum")
        )

        # Previous Averages for Growth Rate Calculation
        prev_daily_avg = Dht11.objects.filter(dt__date=yesterday.date()).aggregate(
            avg_temp=Avg("temp"), avg_hum=Avg("hum")
        )
        prev_weekly_avg = Dht11.objects.filter(
            dt__range=[last_week_start, one_week_ago]
        ).aggregate(avg_temp=Avg("temp"), avg_hum=Avg("hum"))
        prev_monthly_avg = Dht11.objects.filter(
            dt__range=[last_month_start, one_month_ago]
        ).aggregate(avg_temp=Avg("temp"), avg_hum=Avg("hum"))

        # Calculate Growth Rates
        def calculate_growth(current, previous):
            if current is not None and previous is not None and previous != 0:
                return ((current - previous) / previous) * 100
            return None

        daily_hum_growth = calculate_growth(daily_avg["avg_hum"], prev_daily_avg["avg_hum"])
        daily_temp_growth = calculate_growth(
            daily_avg["avg_temp"], prev_daily_avg["avg_temp"]
        )

        weekly_hum_growth = calculate_growth(
            weekly_avg["avg_hum"], prev_weekly_avg["avg_hum"]
        )
        weekly_temp_growth = calculate_growth(
            weekly_avg["avg_temp"], prev_weekly_avg["avg_temp"]
        )

        monthly_hum_growth = calculate_growth(
            monthly_avg["avg_hum"], prev_monthly_avg["avg_hum"]
        )
        monthly_temp_growth = calculate_growth(
            monthly_avg["avg_temp"], prev_monthly_avg["avg_temp"]
        )

        # Average Section
        avg = {
            "daily": {
                "record": {
                    "temp": daily_avg["avg_temp"] or 0,
                    "hum": daily_avg["avg_hum"] or 0,
                    "dt": today.date().isoformat(),
                },
                "humGrow": daily_hum_growth,
                "humTemp": daily_temp_growth,
            },
            "weekly": {
                "record": {
                    "temp": weekly_avg["avg_temp"] or 0,
                    "hum": weekly_avg["avg_hum"] or 0,
                    "dt": one_week_ago.date().isoformat(),
                },
                "humGrow": weekly_hum_growth,
                "humTemp": weekly_temp_growth,
            },
            "monthly": {
                "record": {
                    "temp": monthly_avg["avg_temp"] or 0,
                    "hum": monthly_avg["avg_hum"] or 0,
                    "dt": one_month_ago.date().isoformat(),
                },
                "humGrow": monthly_hum_growth,
                "humTemp": monthly_temp_growth,
            },
        }

        # Extremes for Temperature and Humidity
        lowest_temp_record = (
            Dht11.objects.exclude(temp__isnull=True).order_by("temp").first()
        )
        highest_temp_record = (
            Dht11.objects.exclude(temp__isnull=True).order_by("-temp").first()
        )
        lowest_hum_record = Dht11.objects.exclude(hum__isnull=True).order_by("hum").first()
        highest_hum_record = (
            Dht11.objects.exclude(hum__isnull=True).order_by("-hum").first()
        )

        extremes = {
            "highest": {
                "temp": (
                    DHT11serialize(highest_temp_record).data
                    if highest_temp_record
                    else {"temp": None, "hum": None, "dt": None}
                ),
                "hum": (
                    DHT11serialize(highest_hum_record).data
                    if highest_hum_record
                    else {"temp": None, "hum": None, "dt": None}
                ),
            },
            "lowest": {
                "temp": (
                    DHT11serialize(lowest_temp_record).data
                    if lowest_temp_record
                    else {"temp": None, "hum": None, "dt": None}
                ),
                "hum": (
                    DHT11serialize(lowest_hum_record).data
                    if lowest_hum_record
                    else {"temp": None, "hum": None, "dt": None}
                ),
            },
        }

        # Summary Statistics
        SummaryStatistics = {
            "curr": curr,
            "avg": avg,
            "extremes": extremes,
        }
        
        cache.set("statistics-summary", SummaryStatistics, 60) #caching for 3 hours
        return Response({"data": SummaryStatistics})
    return Response({"data": cashedData})
    


@api_view(["GET"])
def getMonthsAverage(request):
    cashedData = cache.get("months-average")
    if not cashedData:
        # Get the current year
        current_year = timezone.now().year

        # Initialize a list with 12 items for each month
        monthly_averages = [
            {"month": month, "temp": None, "hum": None} for month in range(12)
        ]

        # Get the monthly average of temp and hum
        for month in range(12):
            # Filter records for the specific month and year
            records = Dht11.objects.filter(dt__year=current_year, dt__month=month + 1)

            if records.exists():
                # Calculate the average temp and hum for the month
                avg_temp = records.aggregate(Avg("temp"))["temp__avg"]
                avg_hum = records.aggregate(Avg("hum"))["hum__avg"]

                # Store the result with 2 decimal places
                monthly_averages[month]["temp"] = (
                    round(avg_temp, 2) if avg_temp is not None else None
                )
                monthly_averages[month]["hum"] = (
                    round(avg_hum, 2) if avg_hum is not None else None
                )
        cache.set("months-average",monthly_averages,300)
        return Response({"data": monthly_averages})
    return Response({"data": cashedData})


@api_view(["GET"])
def getDailyAverage(request):
    
    # Get the 'n' days parameter from the request, default to 7 days if not provided
    n_days = int(request.GET.get("n", 7))
    h_hours = int(request.GET.get("h",0))
    cashedData = cache.get("statistics-summary" + str(n_days))
    if not cashedData:
    # Get the current date
        current_date = timezone.now().date()
        daily_averages = []    
        if h_hours > 0 :
            return Response({"data": "24"})            
        # Loop through the last 'n' days
        for i in range(n_days):
            # Calculate the date for each of the last 'n' days
            day_date = current_date - timedelta(days=i)

            # Filter records for the specific day
            records = Dht11.objects.filter(dt__date=day_date)

            if records.exists():
                # Calculate the average temp and hum for the day
                avg_temp = records.aggregate(Avg("temp"))["temp__avg"]
                avg_hum = records.aggregate(Avg("hum"))["hum__avg"]

                # Store the result with 2 decimal places
                daily_averages.append(
                    {
                        "dt": day_date,
                        "temp": round(avg_temp, 2) if avg_temp is not None else None,
                        "hum": round(avg_hum, 2) if avg_hum is not None else None,
                    }
                )
            else:
                # If no records are found for this day, append None for temp and hum
                daily_averages.append(
                    {
                        "dt": day_date,
                        "temp": None,
                        "hum": None,
                    }
                )
        cashedData = cache.set("statistics-summary" + str( n_days),daily_averages,10)
        return Response({"data": daily_averages})
    return Response({"data": cashedData})

    # Initialize a list to store the daily averages

    


class Dhtviews(generics.CreateAPIView):
    queryset = Dht11.objects.all()
    serializer_class = DHT11serialize
