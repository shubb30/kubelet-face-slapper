FROM python:3.8-alpine3.11

ADD requirements.txt /root
ADD run.py /root
RUN pip3 install -r /root/requirements.txt

CMD python /root/run.py
