#! /bin/bash
full_filename=$1
filename="${full_filename%.7z*}.7z"
timestamp=$(date +"%Y-%m-%d_%H:%M:%S")
printf "\n%s filename: %s" "$timestamp" "$filename" >> /home/f2quser/Processed_Thermal_Imagery/log.txt
#if [[ $filename == *.7z ]]; then

dirname="${filename%.*}"
printf "\ndirname: $dirname" >> /home/f2quser/Processed_Thermal_Imagery/log.txt
sleep 10
cp /mnt/data/dmp/$filename /home/f2quser/Processed_Thermal_Imagery/$filename
cd /home/f2quser/Processed_Thermal_Imagery
7z x $filename
rm $filename
cd /home/f2quser/

source /home/f2quser/miniconda3/bin/activate 
printf "\nsource /home/f2quser/miniconda3/bin/activate done" >> /home/f2quser/Processed_Thermal_Imagery/log.txt
conda activate TI_venv
printf "\nconda activate TI_venv done" >> /home/f2quser/Processed_Thermal_Imagery/log.txt
python miniconda3/envs/TI_venv/Scripts/Thermal_Image_Processing/thermal_image_processing.py  $dirname
#python miniconda3/envs/TI_venv/Scripts/test.py
end_timestamp=$(date +"%Y-%m-%d_%H:%M:%S")
printf "\n%s %s done" $end_timestamp $dirname  >> /home/f2quser/Processed_Thermal_Imagery/log.txt
#else printf "\nfilename: $filename" >> /home/f2quser/Processed_Thermal_Imagery/log.txt
#fi
