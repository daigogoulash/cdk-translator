import json
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_s3 as s3,
    aws_iam as iam,
    aws_stepfunctions as sf,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudtrail as cloudtrail,
)
from constructs import Construct

class TranslatorStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # S3 bucket for audio files
        audio_bucket = s3.Bucket(self, "AudioBucket",
                                 removal_policy=RemovalPolicy.DESTROY,
                                 auto_delete_objects=True)

        # S3 bucket for CloudTrail logs
        trail_log_bucket = s3.Bucket(self, "TrailLogBucket",
                                     removal_policy=RemovalPolicy.DESTROY,
                                     auto_delete_objects=True)

        # CloudTrail trail for logging S3 data events
        trail = cloudtrail.Trail(self, "Trail",
                                 is_multi_region_trail=False,
                                 include_global_service_events=False,
                                 management_events=cloudtrail.ReadWriteType.NONE,
                                 bucket=trail_log_bucket)

        trail.add_s3_event_selector(
            s3_selector=[{
                "bucket": audio_bucket,
                "object_prefix": "",
            }],
            include_management_events=False,
            read_write_type=cloudtrail.ReadWriteType.WRITE_ONLY
        )

        # IAM role for Step Functions
        role = iam.Role(self, "StateMachineRole",
                        assumed_by=iam.ServicePrincipal("states.amazonaws.com"))

        # Add policies to the IAM role with least privilege
        role.add_to_policy(iam.PolicyStatement(
            resources=[audio_bucket.bucket_arn, f"{audio_bucket.bucket_arn}/*"],
            actions=[
                "s3:GetObject",
                "s3:PutObject"
            ]
        ))

        role.add_to_policy(iam.PolicyStatement(
            resources=[f"arn:aws:transcribe:{self.region}:{self.account}:transcription-job/*"],
            actions=[
                "transcribe:StartTranscriptionJob",
                "transcribe:GetTranscriptionJob"
            ]
        ))

        role.add_to_policy(iam.PolicyStatement(
            resources=["*"],  # Translate does not support resource-level permissions, so using "*" is necessary
            actions=[
                "translate:TranslateText"
            ]
        ))

        # Ensure Polly permissions are correctly scoped
        role.add_to_policy(iam.PolicyStatement(
            resources=["*"],  # Use "*" for Polly permissions since Polly actions are global
            actions=[
                "polly:StartSpeechSynthesisTask",
                "polly:GetSpeechSynthesisTask"
            ]
        ))

        # Load the state machine definition JSON and replace placeholders with actual bucket names
        with open('assets/state_machine.json', 'r') as f:
            state_machine_definition = json.load(f)

        # Replace placeholders
        state_machine_definition_str = json.dumps(state_machine_definition)
        state_machine_definition_str = state_machine_definition_str.replace('{{AUDIO_BUCKET}}', audio_bucket.bucket_name)
        state_machine_definition = json.loads(state_machine_definition_str)

        # Create the state machine definition
        state_machine_definition_body = sf.DefinitionBody.from_string(json.dumps(state_machine_definition))

        # State machine definition from the modified JSON
        state_machine = sf.StateMachine(
            self, "StateMachine",
            state_machine_name="AudioTranslation",
            definition_body=state_machine_definition_body,
            role=role
        )

        # Event rule to trigger the state machine on S3 object creation via CloudTrail
        rule = events.Rule(self, "Rule",
                           event_pattern=events.EventPattern(
                               source=["aws.s3"],
                               detail_type=["AWS API Call via CloudTrail"],
                               detail={
                                   "eventSource": ["s3.amazonaws.com"],
                                   "eventName": ["PutObject", "CompleteMultipartUpload"],
                                   "requestParameters": {
                                       "bucketName": [audio_bucket.bucket_name],
                                       "x-amz-storage-class": [{"exists": True}]
                                   }
                               }
                           ))

        rule.add_target(targets.SfnStateMachine(state_machine))

        # Grant necessary permissions
        audio_bucket.grant_read_write(state_machine.role)

