# Generated by https://smithery.ai. See: https://smithery.ai/docs/config#dockerfile
# Use the official Python image from the Docker Hub
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Environment variables
ENV QB_TIME_ACCESS_TOKEN="your_access_token_here"
ENV NODE_ENV=development

# Make port 80 available to the world outside this container
EXPOSE 80

# Run main.py when the container launches
CMD ["python", "main.py"]