import os
import time
import boto3
import logging

from datadog_lambda.metric import lambda_metric
from datetime import datetime, timedelta

class AutoScaling:

    def __init__(self, event):
        self.cluster = event['cluster']
        self.service = event['service']
        self.load_balancer = event['load_balancer']
        self.target_group = event['target_group']

        self.minimum = int(event['minimum'])
        self.maximum = int(event['maximum'])
        self.threshold = int(event['threshold'])
        self.scale_down_delay_in_seconds = int(event['scale_down_delay_in_seconds'])

        self.s3_client = boto3.client('s3')
        self.ecs_client = boto3.client('ecs')
        self.cloudwatch_client = boto3.client('cloudwatch')

    def get_request_count_per_target(self):
        start_time = datetime.now() - timedelta(seconds=300)
        end_time = datetime.now()

        response = self.cloudwatch_client.get_metric_statistics(
            Namespace='AWS/ApplicationELB',
            MetricName='RequestCountPerTarget',
            Dimensions=[
                {
                    'Name': 'LoadBalancer',
                    'Value': self.load_balancer
                },
                {
                    'Name': 'TargetGroup',
                    'Value': self.target_group
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=60,
            Statistics=['Sum']
        )

        # sort the response by the Timestamp of each metric in descending order
        sorted_response = sorted(response['Datapoints'], key=lambda x: x['Timestamp'], reverse=True)

        # return the last 2 item from the sorted response
        # this is needed because sometimes the latest metrics becomes messy so its more failsafe to get the 2 last.
        return int(sorted_response[-2]['Sum'])

    def get_desired_and_pending_count(self):
        response = self.ecs_client.describe_services(
            cluster=self.cluster,
            services=[self.service]
        )

        return response['services'][0]['desiredCount'], response['services'][0]['pendingCount']

    def calculate_new_desired_count(self, current_desired_count, pending_count, request_count_per_target):
        if request_count_per_target > self.threshold:
            if (request_count_per_target - self.threshold) < 30:
                return current_desired_count

            # scaling up
            diff = (request_count_per_target - self.threshold) * current_desired_count

            containers_to_scale_up = int(diff / self.threshold)

            if pending_count == 0:
                new_desired_count = current_desired_count + containers_to_scale_up

            elif containers_to_scale_up > pending_count:
                new_desired_count = current_desired_count + (containers_to_scale_up - pending_count)

            else:
                return current_desired_count

            if new_desired_count > self.maximum:
                return self.maximum
            elif new_desired_count < self.minimum:
                return self.minimum

            return new_desired_count
        else:
            # scaling down
            diff = (self.threshold - request_count_per_target) * current_desired_count

            containers_to_scale_down = int(diff / self.threshold)

            # prevent scaling down more than MAX_CONTAINERS_TO_SCALE_DOWN at a time
            max_containers_to_scale_down = int(os.environ['MAX_CONTAINERS_TO_SCALE_DOWN'])

            if containers_to_scale_down > max_containers_to_scale_down:
                containers_to_scale_down = max_containers_to_scale_down

            new_desired_count = current_desired_count - containers_to_scale_down

            if new_desired_count < self.minimum:
                return self.minimum

            return new_desired_count

    def __seconds_until_last_scale_down(self):
        obj = self.s3_client.get_object(
            Bucket=os.environ['S3_BUCKET_NAME'],
            Key=f'{self.service}-scale-down-delay.txt'
        )

        last_scale_down_time = datetime.fromtimestamp(
            float(obj['Body'].read().decode())
        )

        now_time = datetime.now()

        now_unix_timestamp = time.mktime(now_time.timetuple())
        last_scale_down_timestamp = time.mktime(last_scale_down_time.timetuple())

        return int(now_unix_timestamp - last_scale_down_timestamp)

    def __write_timestamp_to_file(self):
        timestamp = datetime.now().timestamp()

        self.s3_client.put_object(
            Body=str(timestamp).encode(),
            Bucket=os.environ['S3_BUCKET_NAME'],
            Key=f'{self.service}-scale-down-delay.txt'
        )


    def __update_ecs_service(self, new_desired_count):
        print(f'---- Updating {self.service} service to {new_desired_count} containers.')

        self.ecs_client.update_service(
            cluster=self.cluster,
            service=self.service,
            desiredCount=new_desired_count
        )

    def write_datadog_metric(self, direction, new_desired_count):
        lambda_metric(
            "aws.lambda.auto_scaling.desired_count",
            new_desired_count,
            tags=[f"service:{self.service}", f"cluster:{self.cluster}", f"direction:{direction}"]
        )

    def scale_down(self, new_desired_count):
        try:
            diff_in_seconds = self.__seconds_until_last_scale_down()

            print(f'---- Seconds passed until the last scale down activity: {diff_in_seconds}s')

            if diff_in_seconds > int(self.scale_down_delay_in_seconds):
                self.write_datadog_metric("down", new_desired_count)

                self.__update_ecs_service(new_desired_count)

                self.__write_timestamp_to_file()
            else:
                print(f'---- Last scale down activity is not older than {self.scale_down_delay_in_seconds}s. Not doing anything. Bye bye.')

        except self.s3_client.exceptions.NoSuchKey:
            self.__write_timestamp_to_file()

    def scale_up(self, new_desired_count):
        self.write_datadog_metric("up", new_desired_count)
        self.__update_ecs_service(new_desired_count)
