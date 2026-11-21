@echo off
python tools\run_days.py --cmd "python main.py" --days 1-5 --out runs\workmate
python tools\score.py --run runs\workmate --days 1-5
pause
