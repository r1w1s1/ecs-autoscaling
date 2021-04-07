from datadog_lambda.wrapper import datadog_lambda_wrapper

from autoscaling import AutoScaling

@datadog_lambda_wrapper
def lambda_handler(event, context):
    autoscaling = AutoScaling(event)

    print(f'== Starting autoscaling for {autoscaling.service} on cluster {autoscaling.cluster} ==')

    request_count_per_target = autoscaling.get_request_count_per_target()

    print(f'---- RequestCountPerTarget: {request_count_per_target}, Threshold: {autoscaling.threshold}')

    current_desired_count, pending_count = autoscaling.get_desired_and_pending_count()

    new_desired_count = autoscaling.calculate_new_desired_count(current_desired_count, pending_count, request_count_per_target)

    if current_desired_count > new_desired_count:
        print(f'---- Scaling down activity started. DesiredCount: {current_desired_count}, New Desired Count: {new_desired_count}')

        autoscaling.scale_down(new_desired_count)

    elif current_desired_count < new_desired_count:
        print(f'---- Scaling up activity started. DesiredCount: {current_desired_count}, New Desired Count: {new_desired_count}')

        autoscaling.scale_up(new_desired_count)

    else:
        print(f'---- No updates to be performed this time. Bye bye.')

    print(f'== Finished autoscaling for {autoscaling.service} on cluster {autoscaling.cluster} ==')
