## Deploying to Lambda

Inside the main folder, run:

```
$ zip -r lambda_function.zip .
```

and then upload the package into Lambda console. Or in terminal run:

```
$ aws lambda update-function-code --function-name alb_service_auto_scaling --zip-file fileb://lambda_function.zip
```

#### Required payload to run function

```json
{
  "cluster": "<your cluster name>",
  "service": "<your service name>",
  "load_balancer": "<your balancer namespace: app/XXXXX-XXXXXX/999999999>",
  "target_group": "<your target group namespace: targetgroup/XXXXX-XXXXXX/999999999>",
  "minimum": "<minimum number of containers to scale down>",
  "maximum": "<maximum number of containers to scale up>",
  "threshold": "<value used to scale down/up. the script will always try to get as close as possible to this value>",
  "scale_down_delay_in_seconds": "<delay between scale down activities>"
}
```

#### Required environment variables

- S3_BUCKET_NAME: bucket to save the delay file containing the timestamp
- MAX_CONTAINERS_TO_SCALE_DOWN: maximum number of containers to scale down at a single time
- DD_API_KEY: api key from datadog used to write custom metrics
