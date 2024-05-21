From ubuntu:latest

RUN apt-get update
RUN apt-get install python3-pip nano -y
RUN pip install pyyaml
RUN pip install kubernetes
RUN pip install Flask

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8

RUN pip3 install redis
RUN pip install python-dotenv

# Creating Application Source Code Directory
RUN mkdir -p /home/iccs/panos/iarm

# Setting Home Directory for containers
WORKDIR /home/iccs/panos/iarm

# Copying src code ('iarm' folder) to Container
COPY iarm /home/iccs/panos/iarm

# Exposing Ports
EXPOSE 5035

# Running Python Application
#CMD ["python3", "iarm_new_v1.py"]
CMD ["python3", "-u", "iarm_new_v3.6.1.py"]
#CMD ["sleep", "infinity"]
