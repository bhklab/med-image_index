#!/bin/bash

# create_release.sh
# Script to run index_tcia.py with date (today - 1 month) and then create_new_release.py

# Get current year, month, day
year=$(date +%Y)
month=$(date +%m)
day=$(date +%d)

# Subtract 1 month
if [ $month -eq 1 ]; then
    # If January, go to December of previous year
    month=12
    year=$((year - 1))
else
    month=$((month - 1))
fi

# Ensure month has 2 digits
month=$(printf "%02d" $month)

# Get the last day of the target month
# This handles cases where current day doesn't exist in the target month
max_day=$(date -d "$year-$month-01 +1 month -1 day" +%d 2>/dev/null || echo "28")

# If current day is greater than max day of target month, use max day
if [ $day -gt $max_day ]; then
    day=$max_day
fi

# Format day with leading zero
day=$(printf "%02d" $day)

# Final date in dd/mm/yyyy format
formatted_date="${day}/${month}/${year}"

echo "Running index_tcia.py with date: $formatted_date"

# Run the first command
if pixi run workflow/scripts/index_tcia.py --date "$formatted_date"; then
    echo "✓ index_tcia.py completed successfully"
else
    echo "✗ Error: index_tcia.py failed"
    exit 1
fi

echo ""
echo "Running create_new_release.py"

# Run the second command
if pixi run workflow/scripts/create_new_release.py; then
    echo "✓ create_new_release.py completed successfully"
else
    echo "✗ Error: create_new_release.py failed"
    exit 1
fi

echo ""
echo "✓ All tasks completed successfully!"