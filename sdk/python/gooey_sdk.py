import asyncio
import aiohttp
import requests
import traceback
from pydantic import BaseModel, ValidationError
from urllib.error import HTTPError
import os
from dotenv import load_dotenv, find_dotenv
import models
from pathlib import Path

BASE_URL = 'https://api.gooey.ai'

class GooeyAi:
  '''
    Initializes the GooeyAi object, loading the API key from the .env file or the environment.
  '''
  def __init__(self):
    load_dotenv(find_dotenv())
    self.api_key = os.getenv('GOOEY_API_KEY')
    if not self.api_key:
      raise ValueError("GOOEY_API_KEY environment variable not found in .env or set in environment variables. Please set it to your Gooey API key.")
    
  def __get_documents_array(self, path: str) -> list[str]:
    path = Path(path)
    
    files  = []
    for file in path.iterdir():
        if file.is_file():
            files.append(("documents", open(file, "rb")))
            print("Added " + str(file) + " to files")
    return files 
  
  '''
    Builds a request object of the given request_class
    Args:
      request_class: The request class to build
      kwargs: The values provided by the user
    Returns:
      The built request object of type request_class. Is typesafe and will raise an error if the request object is not valid.
    Raises:
      ValidationError: If the request object is not valid, a ValidationError will be raised with the error message.
  '''
  def __build_request_model(self, request_class: BaseModel, **kwargs) -> tuple[BaseModel, list]:
    
    for key in request_class.__fields__.items():
      if key[0] not in kwargs:
        kwargs[key[0]] = models.NotGiven()
    
    if 'input_documents' in kwargs and not isinstance(kwargs['input_documents'], list):
      try:
        kwargs['input_documents'] = self.__get_documents_array(kwargs['input_documents'])
      except Exception as e:
        print(f"An error occurred while getting the documents: {e}")
    request = request_class.parse_obj(kwargs)
    
    return request
  '''
  Makes a request to the API, and returns the response object of the given response_class, which is typesafe and a valid response.
  Args:
    endpoint: The endpoint to make the request to
    response_class: The response class to build
    api_key: The API key to authenticate the request
    request: The request object to send
  Returns:
    A tuple containing two objects: the MetaInfo and the response object of type response_class. Is typesafe and will raise an error 
    if either of the objects are not valid.
  Raises:
    HTTPError: If the response is not ok, an HTTPError will be raised with the status code.
    ValidationError: If the response object is not valid, a ValidationError will be raised with the error message.
  '''
  def __get_response_model(self, endpoint: str, response_class: BaseModel, api_key: str, request: BaseModel) -> tuple[BaseModel, BaseModel]:
    request_dict = self.__strip_not_given(request)
    
    response = requests.post(
      BASE_URL + endpoint,
      headers = {
        "Authorization": f"Bearer {api_key}"
      },
      json = request_dict
    )
        
    response_json = response.json()
    if response.status != 200:
      raise HTTPError(endpoint, response.status, response.read, response.headers, None)

    base_response = models.MetaInfoResponse.parse_obj(response_json)
    response_model = response_class.parse_obj(response_json["output"])
    
    return (base_response, response_model)
  
  def ask_copilot(self, input_prompt: str, **kwargs) -> tuple[models.MetaInfoResponse, models.VideoBotsResponse]:
    try:
      request = self.__build_request_model(models.VideoBotsRequest, input_prompt=input_prompt, **kwargs)
      meta, response = self.__get_response_model('/v2/video-bots', models.VideoBotsResponse, self.api_key, request)
      return meta, response
    except ValidationError as e:
      print(f"An type error occurred while making the request: {e}")
    except HTTPError as e:
      print(f"An HTTP error occurred while making the request: {e}")
    except Exception as e:
      tb = traceback.format_exc()
      print(f"An error occurred: {e}\n{tb}")