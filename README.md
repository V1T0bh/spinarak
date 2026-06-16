# Spinarak, a semi-automated booking bot for Tokyo's Pokemon Cafe

## What it'll do:
1. Regularly check for days with open reservation slots within the next month
2. If a day with availability is found, an email is sent to you with the booking link and a screenshot showing the available slot(s) found

You still have to manually complete the last step in the booking process. For this reason, I highly recommend having push notifcations enabled on your phone email app. This way you can click the reservation link that gets automatically emailed to you ASAP.

Spinarak uses Selenium WebDriver with headless Chrome to get around the Pokemon Cafe's site anti-automation controls. You won't be able to easily parse the server responses using curl or similar.

For fun, Spinarak stores screenshots of hits under the `/hits/` directory of the repo.

## How to set Spinarak up
1. Fork this repo
2. Create a [Gmail app password](https://myaccount.google.com/apppasswords)
3. Go to your forked Spinarak repo > `Settings` > `Secrets and variables` >  `Actions` > `Secrets`
4. Store your GMail settings as GitHub Action secrets:
  - `GMAIL_APP_PW`
  - `GMAIL_RECIPIENT`
  - `GMAIL_RECIPIENT_2` (optional)
  - `GMAIL_SENDER`
4. Update the `cron` line on `spinarak.yml` to suit your needs. The more frequent the action runs, the more likely Spinarak will find an open slot
5. By default Spinarak checks Osaka for a party of 2. The current target slots are July 28 at 17:30 or later, July 29 anytime, and July 30 anytime. You can change these by updating `LOCATION`, `NUM_OF_GUESTS`, and `TARGET_SLOT_RULES` in `spinarak.py`

## Billing portential warning
Please note that if you fork this repo as a private repo, you may go above your free Actions minutes which means **you'll be billed**.

## Have fun at Pokemon Cafe!
If everything goes well, you'll book your slot and get to meet Pikachu just like we did!

https://github.com/user-attachments/assets/8a33b716-2799-4efc-826d-a184892d3b1a
