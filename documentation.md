Windows passar pro wsl o rpi

```
# lista os devices conectados ao usb do windows
usbipd list
```

```
# Marca o device para ser compartilhado
usbipd bind --busid 1-9
```


```
# adiciona o device ao WSL
usbipd attach --wsl --busid 1-9
```