# Encryption

## at-rest — Data at rest
All customer data at rest is encrypted with AES-256. This covers the primary analytics
database, object storage for uploaded files, and database snapshots. Encryption at rest is
enabled by default and cannot be turned off by customers or by Quillmere staff.

## in-transit — Data in transit
Customer data in transit over public networks is encrypted with TLS 1.2 or higher.
Connections that offer an older protocol version are refused. Traffic between internal
services inside the production network is also encrypted with TLS.

## key-management — Key management
Encryption keys are stored in a managed key service and are never written to application
servers. Data encryption keys are rotated every 12 months. Access to key administration is
limited to the infrastructure team and every key operation is logged.

## customer-managed-keys — Customer-managed keys
Customer-managed encryption keys are available on the Enterprise plan only. When a customer
revokes its key, the affected data becomes unreadable to Quillmere within one hour.
