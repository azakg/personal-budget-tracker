!#/bin/sh
for region in $(aws ec2 describe-regions --query "Regions[].RegionName" --output text); do
  echo "--- $region ---"
  aws eks list-clusters --region $region
  aws ec2 describe-vpcs --region $region --filters "Name=tag:Name,Values=budget-vpc" --query "Vpcs[].VpcId"
done
