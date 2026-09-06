@echo off
REM VerdictAI-Now one-click dev wrapper
REM Usage:  dev          (with seed data)
REM         dev -NoSeed  (skip seed data)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" %*
