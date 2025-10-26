from icalendar import Calendar, Event, vText, vCalAddress
from django.utils import timezone
import uuid

def build_ics_for_booking(booking):
    cal = Calendar()
    cal.add('prodid', '-//PC Lab Booking//example.org//')
    cal.add('version', '2.0')

    ev = Event()
    ev.add('uid', f"booking-{booking.pk}@{booking.lab.name}")
    ev.add('summary', f"Lab booking: {booking.lab.name}")
    ev.add('dtstart', booking.start)
    ev.add('dtend', booking.end)
    ev.add('dtstamp', timezone.now())
    ev.add('description', booking.purpose or '')
    organizer = vCalAddress(f'MAILTO:{booking.requester.email}')
    organizer.params['cn'] = vText(booking.requester.get_full_name() or booking.requester.email)
    ev['organizer'] = organizer

    # Add attendees if you want (e.g., approver)
    # ev.add('attendee', vCalAddress('MAILTO:approver@example.org'))

    cal.add_component(ev)
    return cal.to_ical()
