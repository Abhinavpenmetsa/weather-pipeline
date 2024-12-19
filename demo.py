from pprint import pprint
import requests
import pymongo
from datetime import datetime, timedelta

# Get details of all cities from mongo collection
# Database: weather db
# Collection: city_coordinates
def get_all_cities():
    print('Getting city coordinates')

    # Connect to MongoDB and details for all cities
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['weather_db']
    collection = db['city_coordinates']

    # Get details for all cities in the collection into a list called as city details
    results = collection.find()
    all_cities = []
    for result in results:
        all_cities.append(result)
    return all_cities

# Get data from source (open-meteo)
def read_weather_data(city,start_date,end_date):
    """
       Read weather data from open-meteo
       Use city coordinates to get weather data
       url: https://api.open-meteo.com/v1/forecast

    """
    print(f'Reading Weather Data for city: {city["city"]} and date: {start_date}')
    params ={
        "latitude": city['latitude'],
        "longitude": city['longitude'],
        "hourly": ["temperature_2m", "precipitation", "rain"],
        "start_date": start_date,
        "end_date": end_date
    }
    response = requests.get('https://api.open-meteo.com/v1/forecast', params=params)
    if response.status_code == 200:
        weather_data = response.json()
        return weather_data
    else:
        return None

 # Process data
def process_weather_data(city_name, date, weather_data):
    print(f'Processing Weather Data for city: {city_name} and date: {date}')
    
    document = {
            "city": city_name,
            "date": date
        }
    
    data = []


    for i, time_string in enumerate(weather_data['hourly']['time']):
        date, hour = time_string.split('T')
        hour = hour.split(':')[0]  # Extracting just the hour part

        data.append({
            "hour": int(hour),
            "temperature_2m": weather_data['hourly']['temperature_2m'][i],
            "precipitation": weather_data['hourly']['precipitation'][i],
            "rain": weather_data['hourly']['rain'][i]
            })


    document['data'] = data
    return document

# Load data into Mongodb
def load_weather_data(weather_data_list, start_date):
    """
       Populate weather_data_list into Mongodb
       Database: weather_db
       Collection: city_weather_hourly
    """
    print(f'Loading weather data into MongoDB for date: {start_date}')
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['weather_db']
    collection = db['city_weather_hourly']
    collection.insert_many(weather_data_list)

def delete_weather_data(start_date):
    """
       Delete weather data for a given date from Mongodb
       Database: weather_db
       Collection: city_weather_hourly
    """
    print(f'Deleting Weather Data from MongoDB for date: {start_date}')
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['weather_db']
    collection = db['city_weather_hourly']
    collection.delete_many({"date": start_date})   

def get_pipeline_checkpoint():
    """
       Get pipeline checkpoint details from Mongodb
       Database: weather_db
       Collection: pipeline_checkpoints
    """
    print('Getting pipeline checkpoint details')
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['weather_db']
    collection = db['pipeline_checkpoints']
    result = collection.find_one({"pipeline_name": "weather_data_ingestion"})
    return result
    

def update_pipeline_checkpoint(weather_data_list, start_date):
    """
       Update pipeline checkpoint details in Mongodb (insert or update)
       Database: weather_db
       Collection: pipeline_checkpoints
    """

    print(f'Updating pipeline checkpoint details for date: {start_date}')
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['weather_db']
    collection = db['pipeline_checkpoints']

    # Check if pipeline checkpoint exists for the given date
    result = collection.find_one({"pipeline_name": "weather_data_ingestion"})
    
    # next_run should be incremented by 1 day based on the last_processed_date or start_date
    # Calculate the next run date
    if result and 'last_processed_date' in result:
        last_next_run = datetime.strptime(result['next_run'], '%Y-%m-%d')
        next_run = last_next_run + timedelta(days=1)
    else:
        next_run = datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=1)

    next_run = next_run.strftime('%Y-%m-%d')

    if result:
        # Update the existing pipeline checkpoint
        collection.update_one(
            {"pipeline_name": "weather_data_ingestion"},
            {
                "$set": {
                    "last_run": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "status": "completed",
                    "last_processed_city": weather_data_list[-1]['city'],
                    "last_processed_date": start_date,
                    "next_run": next_run,
                    "comments": f"Successfully ingested data for all configured cities for {start_date}."
                }
            }
        )
    else:
        # Insert a new pipeline checkpoint
        collection.insert_one({
            "pipeline_name": "weather_data_ingestion",
            "last_run": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status": "completed",
            "last_processed_city": weather_data_list[-1]['city'],
            "last_processed_date": start_date,
            "next_run": next_run,
            "comments": f"Successfully ingested data for all configured cities for {start_date}."
        })

def add_pipeline_run_history(weather_data_list, start_date, job_run_start_time):
    """
       Add pipeline run history details in Mongodb
       Database: weather_db
       Collection: pipeline_run_history
    """
    print(f'Adding pipeline run history details for date: {start_date}')
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['weather_db']
    collection = db['pipeline_run_history']
    pipeline_run_data = {
        "pipeline_name": "weather_data_ingestion",
        "run_date": start_date,
        "start_time": job_run_start_time,
        "end_time": datetime.now().strftime('%Y-%m-%dT%H:%M:%Sz'),
        "status": "completed",
        "processed_cities": [],
        "success_count": 0,
        "failure_count": 0,
        "errors": []
    }
    for weather_data in weather_data_list:
        pipeline_run_data["processed_cities"].append({
            "name": weather_data["city"],
            "date": start_date
        })
        pipeline_run_data["success_count"] += 1

    collection.insert_one(pipeline_run_data)

def main():
    print('In main fucntion')
    job_run_start_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%Sz')
    all_cities = get_all_cities()
    weather_data_list = []
    for city in all_cities:
        checkpoint = get_pipeline_checkpoint()
        if checkpoint:
            start_date = checkpoint['next_run']
            end_date = checkpoint['next_run']
        else:
            start_date = '2024-06-01'
            end_date = '2024-06-01'
        weather_data = read_weather_data(city, start_date, end_date)
        weather_data_processed = process_weather_data(city['city'], start_date, weather_data)
        weather_data_list.append(weather_data_processed)    
    delete_weather_data(start_date)  
    load_weather_data(weather_data_list,start_date)
    update_pipeline_checkpoint(weather_data_list, start_date)
    add_pipeline_run_history(weather_data_list,start_date, job_run_start_time)

if __name__ == '__main__':
    print('Invoking Main function')
    main()