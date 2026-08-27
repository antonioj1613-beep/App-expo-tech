"""
Seed the full 15-level TOEIC vocabulary catalog into SkillLesson.

Replaces the entire existing Vocabulary catalog on every run (--replace
semantics, always on): deletes all SkillLesson rows for skill=vocabulary
first, then recreates the full 270-word set below via the same per-item
create() loop pattern the other seed_*.py commands use (not bulk_create --
that would skip the post_save signal that keeps Skill.total_lessons synced,
see signals.sync_skill_lesson_count). Cascades UserSkillLessonCompletion /
UserVocabularyReviewState for any learner who had reviewed the old catalog
-- expected and accepted for this migration (see content-migration design
doc).

Level -> CEFR band matches gamification.LESSON_LEVEL_TO_CEFR_BAND exactly:
1-2 A1, 3-4 A2, 5-7 B1, 8-9 B2, 10-12 C1, 13-15 C2.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from app.models import Skill, SkillLesson

VOCABULARY_LESSON_SEED = [
    # --- Level 1 -- A1 -- everyday people, places, basics ---------------
    {"vocab_word": "Friend", "vocab_ipa": "/frend/", "vocab_meaning": "A person you know well and like.", "vocab_example": "She met her best friend in high school.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Family", "vocab_ipa": "/ˈfæməli/", "vocab_meaning": "A group of people related to each other, such as parents and children.", "vocab_example": "My family lives in a small town.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "House", "vocab_ipa": "/haʊs/", "vocab_meaning": "A building where a person or family lives.", "vocab_example": "They bought a new house last year.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Work", "vocab_ipa": "/wɜːrk/", "vocab_meaning": "A job or activity done to earn money.", "vocab_example": "He goes to work by bus every day.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "School", "vocab_ipa": "/skuːl/", "vocab_meaning": "A place where children go to learn.", "vocab_example": "Her daughter starts school in September.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Morning", "vocab_ipa": "/ˈmɔːrnɪŋ/", "vocab_meaning": "The early part of the day.", "vocab_example": "I always drink coffee in the morning.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Night", "vocab_ipa": "/naɪt/", "vocab_meaning": "The time when it is dark outside.", "vocab_example": "We arrived at the hotel late at night.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Food", "vocab_ipa": "/fuːd/", "vocab_meaning": "Things that people eat.", "vocab_example": "The restaurant serves great local food.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Water", "vocab_ipa": "/ˈwɔːtər/", "vocab_meaning": "The clear liquid people drink.", "vocab_example": "Please bring a bottle of water with you.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Book", "vocab_ipa": "/bʊk/", "vocab_meaning": "Pages with words, bound together to read.", "vocab_example": "He is reading a book about history.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Phone", "vocab_ipa": "/foʊn/", "vocab_meaning": "A device used to call or message people.", "vocab_example": "Can I use your phone to call a taxi?", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Car", "vocab_ipa": "/kɑːr/", "vocab_meaning": "A vehicle used to travel on roads.", "vocab_example": "We rented a car for the trip.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "City", "vocab_ipa": "/ˈsɪti/", "vocab_meaning": "A large town where many people live.", "vocab_example": "New York is a very busy city.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Street", "vocab_ipa": "/striːt/", "vocab_meaning": "A road in a town or city.", "vocab_example": "The bakery is on the next street.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Shop", "vocab_ipa": "/ʃɑːp/", "vocab_meaning": "A small store where things are sold.", "vocab_example": "She works at a clothing shop downtown.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Money", "vocab_ipa": "/ˈmʌni/", "vocab_meaning": "Coins and notes used to buy things.", "vocab_example": "I don't have enough money for a taxi.", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Time", "vocab_ipa": "/taɪm/", "vocab_meaning": "The hours and minutes of the day.", "vocab_example": "What time does the meeting start?", "vocab_cefr": "A1", "level": 1},
    {"vocab_word": "Name", "vocab_ipa": "/neɪm/", "vocab_meaning": "What a person or thing is called.", "vocab_example": "Please write your name on the form.", "vocab_cefr": "A1", "level": 1},

    # --- Level 2 -- A1 -- daily routine, food, travel basics -------------
    {"vocab_word": "Breakfast", "vocab_ipa": "/ˈbrekfəst/", "vocab_meaning": "The first meal of the day.", "vocab_example": "He usually skips breakfast on busy mornings.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Lunch", "vocab_ipa": "/lʌntʃ/", "vocab_meaning": "The meal eaten in the middle of the day.", "vocab_example": "We had lunch together at a nearby café.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Dinner", "vocab_ipa": "/ˈdɪnər/", "vocab_meaning": "The main meal, usually eaten in the evening.", "vocab_example": "They cooked dinner for the whole family.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Weather", "vocab_ipa": "/ˈweðər/", "vocab_meaning": "The condition of the sky and temperature outside.", "vocab_example": "The weather is cold and rainy today.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Weekend", "vocab_ipa": "/ˈwiːkend/", "vocab_meaning": "Saturday and Sunday.", "vocab_example": "We're visiting my parents this weekend.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Holiday", "vocab_ipa": "/ˈhɑːlɪdeɪ/", "vocab_meaning": "A day or period of rest from work or school.", "vocab_example": "The office is closed for the holiday.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Ticket", "vocab_ipa": "/ˈtɪkɪt/", "vocab_meaning": "A piece of paper or pass that lets you travel or enter somewhere.", "vocab_example": "I bought a train ticket to the coast.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Airport", "vocab_ipa": "/ˈeərpɔːrt/", "vocab_meaning": "A place where planes take off and land.", "vocab_example": "We arrived at the airport two hours early.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Hotel", "vocab_ipa": "/hoʊˈtel/", "vocab_meaning": "A building where travelers pay to stay overnight.", "vocab_example": "The hotel offers free breakfast every morning.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Station", "vocab_ipa": "/ˈsteɪʃn/", "vocab_meaning": "A stopping place for trains or buses.", "vocab_example": "Meet me at the station at nine.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Bus", "vocab_ipa": "/bʌs/", "vocab_meaning": "A large vehicle that carries many passengers.", "vocab_example": "She takes the bus to work every day.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Train", "vocab_ipa": "/treɪn/", "vocab_meaning": "A vehicle that runs on tracks and carries passengers.", "vocab_example": "The train to the airport leaves every 20 minutes.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Map", "vocab_ipa": "/mæp/", "vocab_meaning": "A drawing that shows where places are.", "vocab_example": "He checked the map to find the museum.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Passport", "vocab_ipa": "/ˈpæspɔːrt/", "vocab_meaning": "An official document needed to travel to another country.", "vocab_example": "Don't forget to bring your passport to the airport.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Luggage", "vocab_ipa": "/ˈlʌɡɪdʒ/", "vocab_meaning": "Bags and suitcases used for traveling.", "vocab_example": "Please keep your luggage with you at all times.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Restaurant", "vocab_ipa": "/ˈrestrɑːnt/", "vocab_meaning": "A place where people pay to eat meals.", "vocab_example": "We booked a table at a popular restaurant.", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Menu", "vocab_ipa": "/ˈmenjuː/", "vocab_meaning": "A list of food and drinks available at a restaurant.", "vocab_example": "Could I see the menu, please?", "vocab_cefr": "A1", "level": 2},
    {"vocab_word": "Price", "vocab_ipa": "/praɪs/", "vocab_meaning": "The amount of money something costs.", "vocab_example": "The price of the tickets went up this year.", "vocab_cefr": "A1", "level": 2},

    # --- Level 3 -- A2 -- shopping, neighborhood, appointments -----------
    {"vocab_word": "Appointment", "vocab_ipa": "/əˈpɔɪntmənt/", "vocab_meaning": "An arranged time to meet someone or visit somewhere.", "vocab_example": "I have a dentist appointment at 3 p.m.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Receipt", "vocab_ipa": "/rɪˈsiːt/", "vocab_meaning": "A paper proving that you paid for something.", "vocab_example": "Keep your receipt in case you need a refund.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Discount", "vocab_ipa": "/ˈdɪskaʊnt/", "vocab_meaning": "A reduction in the usual price.", "vocab_example": "Students get a 10% discount at the store.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Customer", "vocab_ipa": "/ˈkʌstəmər/", "vocab_meaning": "A person who buys goods or services.", "vocab_example": "The shop tries to respond to every customer quickly.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Cashier", "vocab_ipa": "/kæˈʃɪr/", "vocab_meaning": "A person who takes payments in a shop.", "vocab_example": "The cashier gave me the wrong change.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Delivery", "vocab_ipa": "/dɪˈlɪvəri/", "vocab_meaning": "The act of bringing goods to a person's home or business.", "vocab_example": "The delivery usually arrives within three days.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Package", "vocab_ipa": "/ˈpækɪdʒ/", "vocab_meaning": "A parcel or box sent by mail.", "vocab_example": "I'm expecting a package from the post office.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Address", "vocab_ipa": "/ˈædres/", "vocab_meaning": "The details of where a place or person is located.", "vocab_example": "Please confirm your delivery address before checkout.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Neighbor", "vocab_ipa": "/ˈneɪbər/", "vocab_meaning": "A person who lives near you.", "vocab_example": "Our neighbor kindly watered our plants while we traveled.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Apartment", "vocab_ipa": "/əˈpɑːrtmənt/", "vocab_meaning": "A set of rooms for living in, usually in a larger building.", "vocab_example": "They just moved into a new apartment downtown.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Furniture", "vocab_ipa": "/ˈfɜːrnɪtʃər/", "vocab_meaning": "Movable items like tables and chairs used in a home.", "vocab_example": "We're buying new furniture for the living room.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Kitchen", "vocab_ipa": "/ˈkɪtʃɪn/", "vocab_meaning": "The room where food is cooked.", "vocab_example": "The kitchen was recently renovated.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Bathroom", "vocab_ipa": "/ˈbæθruːm/", "vocab_meaning": "A room with a toilet, sink, and shower or bath.", "vocab_example": "The apartment has two bathrooms.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Garden", "vocab_ipa": "/ˈɡɑːrdn/", "vocab_meaning": "An outdoor area used for growing plants.", "vocab_example": "She spends her weekends working in the garden.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Elevator", "vocab_ipa": "/ˈelɪveɪtər/", "vocab_meaning": "A machine that carries people between floors of a building.", "vocab_example": "The elevator was out of service, so we took the stairs.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Stairs", "vocab_ipa": "/steərz/", "vocab_meaning": "A set of steps between floors.", "vocab_example": "Take the stairs to the second floor.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Parking", "vocab_ipa": "/ˈpɑːrkɪŋ/", "vocab_meaning": "A place where vehicles are left.", "vocab_example": "Parking is free for hotel guests.", "vocab_cefr": "A2", "level": 3},
    {"vocab_word": "Traffic", "vocab_ipa": "/ˈtræfɪk/", "vocab_meaning": "Vehicles moving on a road.", "vocab_example": "Traffic was heavy on the way to the airport.", "vocab_cefr": "A2", "level": 3},

    # --- Level 4 -- A2 -- schedules, health, everyday plans --------------
    {"vocab_word": "Schedule", "vocab_ipa": "/ˈskedʒuːl/", "vocab_meaning": "A plan of times for events or tasks.", "vocab_example": "My schedule is full this week.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Calendar", "vocab_ipa": "/ˈkælɪndər/", "vocab_meaning": "A chart showing days, weeks, and months.", "vocab_example": "Add the meeting to your calendar.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Reminder", "vocab_ipa": "/rɪˈmaɪndər/", "vocab_meaning": "Something that helps you remember a task or event.", "vocab_example": "I set a reminder to call the client.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Invitation", "vocab_ipa": "/ˌɪnvɪˈteɪʃn/", "vocab_meaning": "A written or spoken request for someone to attend an event.", "vocab_example": "We received an invitation to the office party.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Celebration", "vocab_ipa": "/ˌselɪˈbreɪʃn/", "vocab_meaning": "An event held to mark a happy occasion.", "vocab_example": "The team held a small celebration for the launch.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Anniversary", "vocab_ipa": "/ˌænɪˈvɜːrsəri/", "vocab_meaning": "The date each year that marks a past event.", "vocab_example": "The company is celebrating its tenth anniversary.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Hobby", "vocab_ipa": "/ˈhɑːbi/", "vocab_meaning": "An activity done for pleasure in one's free time.", "vocab_example": "Photography is his favorite hobby.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Exercise", "vocab_ipa": "/ˈeksərsaɪz/", "vocab_meaning": "Physical activity done to stay healthy.", "vocab_example": "She does exercise every morning before work.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Healthy", "vocab_ipa": "/ˈhelθi/", "vocab_meaning": "Being in good physical condition, or good for the body.", "vocab_example": "Try to eat a healthy lunch during the workday.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Illness", "vocab_ipa": "/ˈɪlnəs/", "vocab_meaning": "A disease or period of poor health.", "vocab_example": "He was absent from work due to illness.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Pharmacy", "vocab_ipa": "/ˈfɑːrməsi/", "vocab_meaning": "A shop where medicine is sold.", "vocab_example": "The pharmacy is open until 9 p.m.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Prescription", "vocab_ipa": "/prɪˈskrɪpʃn/", "vocab_meaning": "A doctor's written order for medicine.", "vocab_example": "She picked up her prescription at the pharmacy.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Doctor", "vocab_ipa": "/ˈdɑːktər/", "vocab_meaning": "A person trained to treat illness.", "vocab_example": "I need to see a doctor about my headache.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Dentist", "vocab_ipa": "/ˈdentɪst/", "vocab_meaning": "A doctor who treats teeth.", "vocab_example": "I have a dentist appointment tomorrow morning.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Nurse", "vocab_ipa": "/nɜːrs/", "vocab_meaning": "A person trained to care for sick people.", "vocab_example": "The nurse checked his blood pressure.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Hospital", "vocab_ipa": "/ˈhɑːspɪtl/", "vocab_meaning": "A place where sick or injured people are treated.", "vocab_example": "She works as a receptionist at the hospital.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Emergency", "vocab_ipa": "/ɪˈmɜːrdʒənsi/", "vocab_meaning": "A sudden, serious situation needing immediate action.", "vocab_example": "In case of emergency, call this number.", "vocab_cefr": "A2", "level": 4},
    {"vocab_word": "Insurance", "vocab_ipa": "/ɪnˈʃʊrəns/", "vocab_meaning": "A system of protection against loss, paid for regularly.", "vocab_example": "Does your job offer health insurance?", "vocab_cefr": "A2", "level": 4},

    # --- Level 5 -- B1 -- office basics -----------------------------------
    {"vocab_word": "Meeting", "vocab_ipa": "/ˈmiːtɪŋ/", "vocab_meaning": "A gathering of people to discuss something.", "vocab_example": "We have a team meeting every Monday morning.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Colleague", "vocab_ipa": "/ˈkɑːliːɡ/", "vocab_meaning": "A person you work with.", "vocab_example": "I asked a colleague to review my report.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Manager", "vocab_ipa": "/ˈmænɪdʒər/", "vocab_meaning": "A person who is in charge of a team or department.", "vocab_example": "The manager approved the new schedule.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Employee", "vocab_ipa": "/ɪmˈplɔɪiː/", "vocab_meaning": "A person who works for a company.", "vocab_example": "Every new employee attends an orientation session.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Deadline", "vocab_ipa": "/ˈdedlaɪn/", "vocab_meaning": "The latest time by which something must be finished.", "vocab_example": "The deadline for the proposal is Friday.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Project", "vocab_ipa": "/ˈprɑːdʒekt/", "vocab_meaning": "A planned piece of work with a specific goal.", "vocab_example": "The marketing project starts next month.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Report", "vocab_ipa": "/rɪˈpɔːrt/", "vocab_meaning": "A written account describing an event or situation.", "vocab_example": "Please send the sales report by noon.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Email", "vocab_ipa": "/ˈiːmeɪl/", "vocab_meaning": "An electronic message sent over the internet.", "vocab_example": "I'll send you an email with the details.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Document", "vocab_ipa": "/ˈdɑːkjumənt/", "vocab_meaning": "A written or printed piece of information.", "vocab_example": "Attach the document before sending the email.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Folder", "vocab_ipa": "/ˈfoʊldər/", "vocab_meaning": "A container used to organize files.", "vocab_example": "Save the file in the shared folder.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Printer", "vocab_ipa": "/ˈprɪntər/", "vocab_meaning": "A machine that produces printed pages.", "vocab_example": "The printer on the third floor is out of paper.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Computer", "vocab_ipa": "/kəmˈpjuːtər/", "vocab_meaning": "An electronic device used for work and information.", "vocab_example": "My computer needs a software update.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Software", "vocab_ipa": "/ˈsɔːftwer/", "vocab_meaning": "Programs used to operate a computer.", "vocab_example": "The company uses new accounting software.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Password", "vocab_ipa": "/ˈpæswɜːrd/", "vocab_meaning": "A secret word or code used to access something.", "vocab_example": "You'll need to reset your password.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Internet", "vocab_ipa": "/ˈɪntərnet/", "vocab_meaning": "The global network used to connect computers.", "vocab_example": "The internet connection in the office is slow today.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Website", "vocab_ipa": "/ˈwebsaɪt/", "vocab_meaning": "A set of pages on the internet.", "vocab_example": "You can find our prices on the website.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Download", "vocab_ipa": "/ˈdaʊnloʊd/", "vocab_meaning": "To copy a file from the internet to your device.", "vocab_example": "Please download the file before the meeting.", "vocab_cefr": "B1", "level": 5},
    {"vocab_word": "Upload", "vocab_ipa": "/ˈʌploʊd/", "vocab_meaning": "To send a file from your device to the internet.", "vocab_example": "Upload the report to the shared drive.", "vocab_cefr": "B1", "level": 5},

    # --- Level 6 -- B1 -- company & career ---------------------------------
    {"vocab_word": "Office", "vocab_ipa": "/ˈɔːfɪs/", "vocab_meaning": "A room or building where people work.", "vocab_example": "Our office is located downtown.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Department", "vocab_ipa": "/dɪˈpɑːrtmənt/", "vocab_meaning": "A section of a company or organization.", "vocab_example": "The finance department reviews all expense reports.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Headquarters", "vocab_ipa": "/ˈhedkwɔːrtərz/", "vocab_meaning": "The main office of a company or organization.", "vocab_example": "The company's headquarters are in Chicago.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Branch", "vocab_ipa": "/bræntʃ/", "vocab_meaning": "A local office of a larger organization.", "vocab_example": "The bank opened a new branch last month.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Client", "vocab_ipa": "/ˈklaɪənt/", "vocab_meaning": "A person or company that uses another company's services.", "vocab_example": "We meet with the client every quarter.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Supplier", "vocab_ipa": "/səˈplaɪər/", "vocab_meaning": "A company that provides goods or materials.", "vocab_example": "We changed suppliers to reduce shipping costs.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Contract", "vocab_ipa": "/ˈkɑːntrækt/", "vocab_meaning": "A written agreement between parties.", "vocab_example": "Please sign the contract before Friday.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Invoice", "vocab_ipa": "/ˈɪnvɔɪs/", "vocab_meaning": "A document requesting payment for goods or services.", "vocab_example": "The invoice is due within thirty days.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Payment", "vocab_ipa": "/ˈpeɪmənt/", "vocab_meaning": "The act of paying for something.", "vocab_example": "Payment can be made by credit card.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Budget", "vocab_ipa": "/ˈbʌdʒɪt/", "vocab_meaning": "A plan for how money will be spent.", "vocab_example": "The marketing budget was increased this year.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Expense", "vocab_ipa": "/ɪkˈspens/", "vocab_meaning": "Money spent on something.", "vocab_example": "Submit your travel expenses by the end of the month.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Salary", "vocab_ipa": "/ˈsæləri/", "vocab_meaning": "Regular payment made to an employee.", "vocab_example": "Her salary increased after the promotion.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Promotion", "vocab_ipa": "/prəˈmoʊʃn/", "vocab_meaning": "An advancement to a higher position at work.", "vocab_example": "He received a promotion after two years.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Interview", "vocab_ipa": "/ˈɪntərvjuː/", "vocab_meaning": "A formal meeting to evaluate a job candidate.", "vocab_example": "The interview is scheduled for Tuesday afternoon.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Resume", "vocab_ipa": "/ˈrezʊmeɪ/", "vocab_meaning": "A document listing a person's work experience and skills.", "vocab_example": "Please attach your resume to the application.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Qualification", "vocab_ipa": "/ˌkwɑːlɪfɪˈkeɪʃn/", "vocab_meaning": "A skill or experience that makes someone suitable for a job.", "vocab_example": "The role requires a qualification in accounting.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Experience", "vocab_ipa": "/ɪkˈspɪriəns/", "vocab_meaning": "Knowledge or skill gained from doing something.", "vocab_example": "She has five years of experience in sales.", "vocab_cefr": "B1", "level": 6},
    {"vocab_word": "Teamwork", "vocab_ipa": "/ˈtiːmwɜːrk/", "vocab_meaning": "Cooperative effort by a group.", "vocab_example": "The project's success depended on strong teamwork.", "vocab_cefr": "B1", "level": 6},

    # --- Level 7 -- B1 -- procedures & requests -----------------------------
    {"vocab_word": "Announcement", "vocab_ipa": "/əˈnaʊnsmənt/", "vocab_meaning": "A public statement giving information.", "vocab_example": "The manager made an announcement about the new policy.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Notice", "vocab_ipa": "/ˈnoʊtɪs/", "vocab_meaning": "A written or printed piece of information displayed publicly.", "vocab_example": "Read the notice on the bulletin board.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Policy", "vocab_ipa": "/ˈpɑːləsi/", "vocab_meaning": "An official rule or course of action.", "vocab_example": "The company updated its remote work policy.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Procedure", "vocab_ipa": "/prəˈsiːdʒər/", "vocab_meaning": "A set way of doing something.", "vocab_example": "Follow the standard procedure for reporting expenses.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Instructions", "vocab_ipa": "/ɪnˈstrʌkʃnz/", "vocab_meaning": "Directions on how to do something.", "vocab_example": "Read the instructions before assembling the desk.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Guideline", "vocab_ipa": "/ˈɡaɪdlaɪn/", "vocab_meaning": "A general rule or piece of advice.", "vocab_example": "The guideline recommends replying within 24 hours.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Feedback", "vocab_ipa": "/ˈfiːdbæk/", "vocab_meaning": "Comments about performance used for improvement.", "vocab_example": "Please give feedback on the draft by Friday.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Suggestion", "vocab_ipa": "/səˈdʒestʃn/", "vocab_meaning": "An idea or plan offered for consideration.", "vocab_example": "She made a helpful suggestion during the meeting.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Complaint", "vocab_ipa": "/kəmˈpleɪnt/", "vocab_meaning": "A statement expressing dissatisfaction.", "vocab_example": "The hotel handled the complaint quickly.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Apology", "vocab_ipa": "/əˈpɑːlədʒi/", "vocab_meaning": "A statement expressing regret.", "vocab_example": "He sent an apology for the delay.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Request", "vocab_ipa": "/rɪˈkwest/", "vocab_meaning": "A polite or formal act of asking for something.", "vocab_example": "I have a request regarding the schedule.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Permission", "vocab_ipa": "/pərˈmɪʃn/", "vocab_meaning": "Formal approval to do something.", "vocab_example": "You need permission to access this file.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Approval", "vocab_ipa": "/əˈpruːvl/", "vocab_meaning": "Official agreement that something can proceed.", "vocab_example": "The budget is waiting for final approval.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Application", "vocab_ipa": "/ˌæplɪˈkeɪʃn/", "vocab_meaning": "A formal request, often in writing.", "vocab_example": "Submit your application before the deadline.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Form", "vocab_ipa": "/fɔːrm/", "vocab_meaning": "A document with blank spaces to fill in information.", "vocab_example": "Please complete the registration form.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Signature", "vocab_ipa": "/ˈsɪɡnətʃər/", "vocab_meaning": "A person's name written by hand to confirm agreement.", "vocab_example": "The contract needs your signature on page three.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Renewal", "vocab_ipa": "/rɪˈnuːəl/", "vocab_meaning": "The act of extending something for a further period.", "vocab_example": "The lease renewal must be signed by June.", "vocab_cefr": "B1", "level": 7},
    {"vocab_word": "Registration", "vocab_ipa": "/ˌredʒɪˈstreɪʃn/", "vocab_meaning": "The act of officially recording something.", "vocab_example": "Conference registration closes next week.", "vocab_cefr": "B1", "level": 7},

    # --- Level 8 -- B2 -- meetings & collaboration ---------------------------
    {"vocab_word": "Negotiate", "vocab_ipa": "/nɪˈɡoʊʃieɪt/", "vocab_meaning": "To discuss something to reach an agreement.", "vocab_example": "We plan to negotiate a better rate with the supplier.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Agreement", "vocab_ipa": "/əˈɡriːmənt/", "vocab_meaning": "A decision reached by two or more parties.", "vocab_example": "Both companies signed the agreement yesterday.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Proposal", "vocab_ipa": "/prəˈpoʊzl/", "vocab_meaning": "A plan or suggestion put forward for consideration.", "vocab_example": "The team submitted a proposal for the new product.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Presentation", "vocab_ipa": "/ˌpriːzenˈteɪʃn/", "vocab_meaning": "A talk given to explain or show something.", "vocab_example": "She gave a presentation on quarterly results.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Conference", "vocab_ipa": "/ˈkɑːnfərəns/", "vocab_meaning": "A large formal meeting, often on a specific topic.", "vocab_example": "The conference attracts professionals from around the world.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Seminar", "vocab_ipa": "/ˈsemɪnɑːr/", "vocab_meaning": "A meeting for discussion or training on a topic.", "vocab_example": "New hires attend a seminar during their first week.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Workshop", "vocab_ipa": "/ˈwɜːrkʃɑːp/", "vocab_meaning": "A practical training session.", "vocab_example": "The workshop focused on improving customer service skills.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Agenda", "vocab_ipa": "/əˈdʒendə/", "vocab_meaning": "A list of items to be discussed at a meeting.", "vocab_example": "Please review the agenda before the call.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Minutes", "vocab_ipa": "/ˈmɪnɪts/", "vocab_meaning": "An official written record of a meeting.", "vocab_example": "I'll send the minutes after the meeting ends.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Attendee", "vocab_ipa": "/əˌtenˈdiː/", "vocab_meaning": "A person who is present at an event.", "vocab_example": "Each attendee received a name badge.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Participant", "vocab_ipa": "/pɑːrˈtɪsɪpənt/", "vocab_meaning": "A person taking part in an activity.", "vocab_example": "All participants must register in advance.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Venue", "vocab_ipa": "/ˈvenjuː/", "vocab_meaning": "The place where an event is held.", "vocab_example": "The venue can hold up to 300 guests.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Itinerary", "vocab_ipa": "/aɪˈtɪnəreri/", "vocab_meaning": "A planned schedule for a trip.", "vocab_example": "Here is the itinerary for your business trip.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Logistics", "vocab_ipa": "/ləˈdʒɪstɪks/", "vocab_meaning": "The detailed planning of a complex event or process.", "vocab_example": "The logistics of the product launch took months to arrange.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Coordinate", "vocab_ipa": "/koʊˈɔːrdɪneɪt/", "vocab_meaning": "To organize different people or things to work well together.", "vocab_example": "She will coordinate the event with the venue staff.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Collaborate", "vocab_ipa": "/kəˈlæbəreɪt/", "vocab_meaning": "To work jointly with others on a task.", "vocab_example": "The two departments collaborated on the report.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Delegate", "vocab_ipa": "/ˈdelɪɡeɪt/", "vocab_meaning": "To give a task or responsibility to someone else.", "vocab_example": "A good manager knows how to delegate tasks.", "vocab_cefr": "B2", "level": 8},
    {"vocab_word": "Supervise", "vocab_ipa": "/ˈsuːpərvaɪz/", "vocab_meaning": "To watch over and direct work or workers.", "vocab_example": "She supervises a team of six people.", "vocab_cefr": "B2", "level": 8},

    # --- Level 9 -- B2 -- business performance --------------------------------
    {"vocab_word": "Productivity", "vocab_ipa": "/ˌproʊdʌkˈtɪvəti/", "vocab_meaning": "The rate at which work is completed efficiently.", "vocab_example": "The new software improved team productivity.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Efficiency", "vocab_ipa": "/ɪˈfɪʃnsi/", "vocab_meaning": "The ability to do something well without wasting time or resources.", "vocab_example": "The new process increased efficiency significantly.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Performance", "vocab_ipa": "/pərˈfɔːrməns/", "vocab_meaning": "How well a person or thing does a task.", "vocab_example": "His performance review is scheduled for next week.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Evaluation", "vocab_ipa": "/ɪˌvæljuˈeɪʃn/", "vocab_meaning": "A judgment about the value or quality of something.", "vocab_example": "The manager completed the annual evaluation.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Achievement", "vocab_ipa": "/əˈtʃiːvmənt/", "vocab_meaning": "Something successfully accomplished.", "vocab_example": "Winning the contract was a major achievement for the team.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Milestone", "vocab_ipa": "/ˈmaɪlstoʊn/", "vocab_meaning": "An important point or stage in progress.", "vocab_example": "Reaching one million users was a key milestone.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Objective", "vocab_ipa": "/əbˈdʒektɪv/", "vocab_meaning": "A goal that someone plans to achieve.", "vocab_example": "Our main objective this quarter is customer retention.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Strategy", "vocab_ipa": "/ˈstrætədʒi/", "vocab_meaning": "A plan designed to achieve a long-term goal.", "vocab_example": "The company revised its marketing strategy.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Competitive", "vocab_ipa": "/kəmˈpetətɪv/", "vocab_meaning": "Involving strong effort to succeed against others.", "vocab_example": "The market has become extremely competitive.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Marketplace", "vocab_ipa": "/ˈmɑːrkɪtpleɪs/", "vocab_meaning": "The area of business activity where goods are bought and sold.", "vocab_example": "The app is a leader in the online marketplace.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Brand", "vocab_ipa": "/brænd/", "vocab_meaning": "A product or company identity recognized by the public.", "vocab_example": "The company invested heavily in its brand image.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Advertisement", "vocab_ipa": "/ˌædvərˈtaɪzmənt/", "vocab_meaning": "A public notice promoting a product or service.", "vocab_example": "The advertisement ran during the evening news.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Campaign", "vocab_ipa": "/kæmˈpeɪn/", "vocab_meaning": "A planned set of activities to achieve a goal.", "vocab_example": "The ad campaign increased sales by 20 percent.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Satisfaction", "vocab_ipa": "/ˌsætɪsˈfækʃn/", "vocab_meaning": "A feeling of pleasure from having expectations met.", "vocab_example": "Customer satisfaction scores improved this year.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Loyalty", "vocab_ipa": "/ˈlɔɪəlti/", "vocab_meaning": "Firm support or allegiance, such as to a brand.", "vocab_example": "The rewards program was designed to build customer loyalty.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Revenue", "vocab_ipa": "/ˈrevənuː/", "vocab_meaning": "Income generated from business activity.", "vocab_example": "Revenue grew by 15 percent last quarter.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Profit", "vocab_ipa": "/ˈprɑːfɪt/", "vocab_meaning": "Financial gain after costs are subtracted.", "vocab_example": "The company reported a strong profit this year.", "vocab_cefr": "B2", "level": 9},
    {"vocab_word": "Expansion", "vocab_ipa": "/ɪkˈspænʃn/", "vocab_meaning": "The process of growing larger.", "vocab_example": "The company is planning an expansion into Europe.", "vocab_cefr": "B2", "level": 9},

    # --- Level 10 -- C1 -- corporate planning -----------------------------------
    {"vocab_word": "Implement", "vocab_ipa": "/ˈɪmplɪment/", "vocab_meaning": "To put a plan or decision into effect.", "vocab_example": "The company will implement the new policy in March.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Feasibility", "vocab_ipa": "/ˌfiːzəˈbɪləti/", "vocab_meaning": "Whether something is possible to do successfully.", "vocab_example": "The team conducted a feasibility study before investing.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Stakeholder", "vocab_ipa": "/ˈsteɪkhoʊldər/", "vocab_meaning": "A person or group with an interest in a business decision.", "vocab_example": "All stakeholders were consulted before the merger.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Initiative", "vocab_ipa": "/ɪˈnɪʃətɪv/", "vocab_meaning": "A new plan or process to achieve something.", "vocab_example": "The sustainability initiative starts next quarter.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Framework", "vocab_ipa": "/ˈfreɪmwɜːrk/", "vocab_meaning": "A basic structure supporting a system or plan.", "vocab_example": "They developed a framework for evaluating suppliers.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Methodology", "vocab_ipa": "/ˌmeθəˈdɑːlədʒi/", "vocab_meaning": "A system of methods used in an activity.", "vocab_example": "The report explains the research methodology in detail.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Allocation", "vocab_ipa": "/ˌæləˈkeɪʃn/", "vocab_meaning": "The distribution of resources for a particular purpose.", "vocab_example": "Budget allocation for training increased this year.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Projection", "vocab_ipa": "/prəˈdʒekʃn/", "vocab_meaning": "An estimate of future figures based on current data.", "vocab_example": "Sales projections for next quarter look promising.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Forecast", "vocab_ipa": "/ˈfɔːrkæst/", "vocab_meaning": "A prediction of future events or trends.", "vocab_example": "The financial forecast was more positive than expected.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Benchmark", "vocab_ipa": "/ˈbentʃmɑːrk/", "vocab_meaning": "A standard used to measure or judge performance.", "vocab_example": "The company set a new industry benchmark for delivery speed.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Compliance", "vocab_ipa": "/kəmˈplaɪəns/", "vocab_meaning": "Following rules, laws, or standards.", "vocab_example": "The audit confirmed full compliance with regulations.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Regulation", "vocab_ipa": "/ˌreɡjuˈleɪʃn/", "vocab_meaning": "An official rule set by an authority.", "vocab_example": "New safety regulations take effect next year.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Liability", "vocab_ipa": "/ˌlaɪəˈbɪləti/", "vocab_meaning": "Legal responsibility for something.", "vocab_example": "The contract limits the company's liability.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Sustainability", "vocab_ipa": "/səˌsteɪnəˈbɪləti/", "vocab_meaning": "The ability to be maintained without depleting resources.", "vocab_example": "Sustainability is now central to the company's strategy.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Infrastructure", "vocab_ipa": "/ˈɪnfrəstrʌktʃər/", "vocab_meaning": "The basic physical and organizational systems needed to operate.", "vocab_example": "The company invested in new IT infrastructure.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Procurement", "vocab_ipa": "/prəˈkjʊrmənt/", "vocab_meaning": "The process of obtaining goods or services.", "vocab_example": "The procurement team negotiated a better contract.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Outsourcing", "vocab_ipa": "/ˈaʊtsɔːrsɪŋ/", "vocab_meaning": "Hiring an outside company to perform a task.", "vocab_example": "Outsourcing customer support reduced operating costs.", "vocab_cefr": "C1", "level": 10},
    {"vocab_word": "Restructuring", "vocab_ipa": "/riːˈstrʌktʃərɪŋ/", "vocab_meaning": "Reorganizing a company's structure or operations.", "vocab_example": "The restructuring resulted in a new management team.", "vocab_cefr": "C1", "level": 10},

    # --- Level 11 -- C1 -- optimization & strategy verbs -------------------------
    {"vocab_word": "Consolidate", "vocab_ipa": "/kənˈsɑːlɪdeɪt/", "vocab_meaning": "To combine separate things into a single, more effective whole.", "vocab_example": "The two departments were consolidated into one.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Diversify", "vocab_ipa": "/daɪˈvɜːrsɪfaɪ/", "vocab_meaning": "To expand into a variety of products or markets.", "vocab_example": "The firm plans to diversify its investment portfolio.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Streamline", "vocab_ipa": "/ˈstriːmlaɪn/", "vocab_meaning": "To make a process simpler and more efficient.", "vocab_example": "They streamlined the approval process to save time.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Prioritize", "vocab_ipa": "/praɪˈɔːrətaɪz/", "vocab_meaning": "To treat something as more important than other things.", "vocab_example": "We need to prioritize customer complaints this week.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Mitigate", "vocab_ipa": "/ˈmɪtɪɡeɪt/", "vocab_meaning": "To make a problem or risk less severe.", "vocab_example": "The plan aims to mitigate financial risk.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Optimize", "vocab_ipa": "/ˈɑːptɪmaɪz/", "vocab_meaning": "To make the best or most effective use of something.", "vocab_example": "The team optimized the website for mobile users.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Facilitate", "vocab_ipa": "/fəˈsɪlɪteɪt/", "vocab_meaning": "To make an action or process easier.", "vocab_example": "A moderator will facilitate the discussion.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Accommodate", "vocab_ipa": "/əˈkɑːmədeɪt/", "vocab_meaning": "To provide for or adapt to someone's needs.", "vocab_example": "The hotel can accommodate large groups.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Substantiate", "vocab_ipa": "/səbˈstænʃieɪt/", "vocab_meaning": "To provide evidence to support a claim.", "vocab_example": "The report failed to substantiate the projected savings.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Differentiate", "vocab_ipa": "/ˌdɪfəˈrenʃieɪt/", "vocab_meaning": "To recognize or show a difference between things.", "vocab_example": "The brand differentiates itself through quality service.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Capitalize", "vocab_ipa": "/ˈkæpɪtəlaɪz/", "vocab_meaning": "To take advantage of an opportunity.", "vocab_example": "The company hopes to capitalize on the new trend.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Incentivize", "vocab_ipa": "/ɪnˈsentɪvaɪz/", "vocab_meaning": "To motivate someone with a reward.", "vocab_example": "Bonuses are used to incentivize strong performance.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Standardize", "vocab_ipa": "/ˈstændərdaɪz/", "vocab_meaning": "To make things consistent according to a set standard.", "vocab_example": "The company standardized its onboarding process.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Formalize", "vocab_ipa": "/ˈfɔːrməlaɪz/", "vocab_meaning": "To make an arrangement official.", "vocab_example": "The two firms formalized their partnership last month.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Rationalize", "vocab_ipa": "/ˈræʃnəlaɪz/", "vocab_meaning": "To reorganize a system to make it more efficient.", "vocab_example": "Management decided to rationalize the supply chain.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Synthesize", "vocab_ipa": "/ˈsɪnθəsaɪz/", "vocab_meaning": "To combine ideas or information into a coherent whole.", "vocab_example": "The report synthesizes data from three departments.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Articulate", "vocab_ipa": "/ɑːrˈtɪkjuleɪt/", "vocab_meaning": "To express an idea clearly and effectively.", "vocab_example": "She articulated the project's goals during the pitch.", "vocab_cefr": "C1", "level": 11},
    {"vocab_word": "Deliberate", "vocab_ipa": "/dɪˈlɪbəreɪt/", "vocab_meaning": "To think carefully about something before deciding.", "vocab_example": "The board will deliberate on the proposal tomorrow.", "vocab_cefr": "C1", "level": 11},

    # --- Level 12 -- C1 -- legal & governance ---------------------------------------
    {"vocab_word": "Discrepancy", "vocab_ipa": "/dɪˈskrepənsi/", "vocab_meaning": "A difference between things that should be the same.", "vocab_example": "There is a discrepancy between the two reports.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Ambiguity", "vocab_ipa": "/ˌæmbɪˈɡjuːəti/", "vocab_meaning": "The quality of having more than one possible meaning.", "vocab_example": "The clause's ambiguity caused confusion during the review.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Correlation", "vocab_ipa": "/ˌkɔːrəˈleɪʃn/", "vocab_meaning": "A mutual relationship between two or more things.", "vocab_example": "There's a clear correlation between training and performance.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Implication", "vocab_ipa": "/ˌɪmplɪˈkeɪʃn/", "vocab_meaning": "A possible effect or consequence of an action.", "vocab_example": "The policy change has implications for all departments.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Disclosure", "vocab_ipa": "/dɪˈskloʊʒər/", "vocab_meaning": "The act of making new or secret information known.", "vocab_example": "Full disclosure of the terms is required by law.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Transparency", "vocab_ipa": "/trænsˈpærənsi/", "vocab_meaning": "Openness and honesty in communication or process.", "vocab_example": "The company values transparency with its shareholders.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Accountability", "vocab_ipa": "/əˌkaʊntəˈbɪləti/", "vocab_meaning": "Being responsible for one's actions and decisions.", "vocab_example": "Managers are held accountable for their team's results.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Governance", "vocab_ipa": "/ˈɡʌvərnəns/", "vocab_meaning": "The system by which an organization is directed and controlled.", "vocab_example": "The report reviews the company's corporate governance.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Jurisdiction", "vocab_ipa": "/ˌdʒʊrɪsˈdɪkʃn/", "vocab_meaning": "The official power to make legal decisions in an area.", "vocab_example": "The contract falls under a different jurisdiction.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Arbitration", "vocab_ipa": "/ˌɑːrbɪˈtreɪʃn/", "vocab_meaning": "A process for settling a dispute outside of court.", "vocab_example": "The dispute was resolved through arbitration.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Litigation", "vocab_ipa": "/ˌlɪtɪˈɡeɪʃn/", "vocab_meaning": "The process of taking legal action.", "vocab_example": "The company avoided litigation by settling early.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Precedent", "vocab_ipa": "/ˈpresɪdənt/", "vocab_meaning": "An earlier decision used as a guide for future cases.", "vocab_example": "The ruling set a precedent for similar contracts.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Indemnity", "vocab_ipa": "/ɪnˈdemnəti/", "vocab_meaning": "Protection against financial loss or legal responsibility.", "vocab_example": "The agreement includes an indemnity clause.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Provision", "vocab_ipa": "/prəˈvɪʒn/", "vocab_meaning": "A condition included in a legal document.", "vocab_example": "The contract contains a provision for early termination.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Clause", "vocab_ipa": "/klɔːz/", "vocab_meaning": "A distinct section of a legal document.", "vocab_example": "Review the confidentiality clause carefully.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Amendment", "vocab_ipa": "/əˈmendmənt/", "vocab_meaning": "A minor change or addition to a document.", "vocab_example": "An amendment to the contract was approved yesterday.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Ratify", "vocab_ipa": "/ˈrætɪfaɪ/", "vocab_meaning": "To formally approve an agreement.", "vocab_example": "Both parties must ratify the treaty.", "vocab_cefr": "C1", "level": 12},
    {"vocab_word": "Waive", "vocab_ipa": "/weɪv/", "vocab_meaning": "To voluntarily give up a right or claim.", "vocab_example": "The landlord agreed to waive the late fee.", "vocab_cefr": "C1", "level": 12},

    # --- Level 13 -- C2 -- advanced professional verbs --------------------------------
    {"vocab_word": "Leverage", "vocab_ipa": "/ˈlevərɪdʒ/", "vocab_meaning": "To use something to maximum advantage.", "vocab_example": "The firm leveraged its brand reputation to enter new markets.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Spearhead", "vocab_ipa": "/ˈspɪrhed/", "vocab_meaning": "To lead an activity or initiative.", "vocab_example": "She will spearhead the company's digital transformation.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Underscore", "vocab_ipa": "/ˌʌndərˈskɔːr/", "vocab_meaning": "To emphasize the importance of something.", "vocab_example": "The report underscores the need for better training.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Galvanize", "vocab_ipa": "/ˈɡælvənaɪz/", "vocab_meaning": "To inspire people into action.", "vocab_example": "The CEO's speech galvanized the sales team.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Cultivate", "vocab_ipa": "/ˈkʌltɪveɪt/", "vocab_meaning": "To develop or improve something over time.", "vocab_example": "The firm works hard to cultivate client relationships.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Foster", "vocab_ipa": "/ˈfɔːstər/", "vocab_meaning": "To encourage the development of something.", "vocab_example": "The open office layout is meant to foster collaboration.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Bolster", "vocab_ipa": "/ˈboʊlstər/", "vocab_meaning": "To support or strengthen something.", "vocab_example": "New hires were brought in to bolster the sales team.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Underpin", "vocab_ipa": "/ˌʌndərˈpɪn/", "vocab_meaning": "To support or form the basis of something.", "vocab_example": "Strong data underpins the company's decisions.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Entail", "vocab_ipa": "/ɪnˈteɪl/", "vocab_meaning": "To involve something as a necessary consequence.", "vocab_example": "The role entails frequent travel abroad.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Encompass", "vocab_ipa": "/ɪnˈkʌmpəs/", "vocab_meaning": "To include a wide range of things.", "vocab_example": "The training program encompasses both theory and practice.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Preclude", "vocab_ipa": "/prɪˈkluːd/", "vocab_meaning": "To prevent something from happening.", "vocab_example": "A signed contract precludes any further negotiation.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Circumvent", "vocab_ipa": "/ˌsɜːrkəmˈvent/", "vocab_meaning": "To find a way around an obstacle or rule.", "vocab_example": "They found a way to circumvent the shipping delay.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Expedite", "vocab_ipa": "/ˈekspədaɪt/", "vocab_meaning": "To make a process happen faster.", "vocab_example": "We paid extra to expedite the delivery.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Curtail", "vocab_ipa": "/kɜːrˈteɪl/", "vocab_meaning": "To reduce or limit something.", "vocab_example": "The company had to curtail spending this quarter.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Forgo", "vocab_ipa": "/fɔːrˈɡoʊ/", "vocab_meaning": "To decide not to have or do something.", "vocab_example": "The board chose to forgo a dividend this year.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Forestall", "vocab_ipa": "/fɔːrˈstɔːl/", "vocab_meaning": "To prevent something by acting in advance.", "vocab_example": "The firm raised prices early to forestall a supply shortage.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Hinge", "vocab_ipa": "/hɪndʒ/", "vocab_meaning": "To depend entirely on a single factor.", "vocab_example": "Success hinges on securing the client's approval.", "vocab_cefr": "C2", "level": 13},
    {"vocab_word": "Warrant", "vocab_ipa": "/ˈwɔːrənt/", "vocab_meaning": "To justify or make necessary.", "vocab_example": "The results warrant a closer investigation.", "vocab_cefr": "C2", "level": 13},

    # --- Level 14 -- C2 -- nuanced reasoning & inference -------------------------------
    {"vocab_word": "Contingency", "vocab_ipa": "/kənˈtɪndʒənsi/", "vocab_meaning": "A possible future event that must be planned for.", "vocab_example": "The budget includes a contingency for unexpected costs.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Exigency", "vocab_ipa": "/ˈeksɪdʒənsi/", "vocab_meaning": "An urgent need or demand.", "vocab_example": "The exigencies of the market forced a quick decision.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Latitude", "vocab_ipa": "/ˈlætɪtuːd/", "vocab_meaning": "Freedom to act or make decisions within limits.", "vocab_example": "Senior staff are given more latitude on scheduling.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Discretion", "vocab_ipa": "/dɪˈskreʃn/", "vocab_meaning": "The freedom to decide what should be done in a situation.", "vocab_example": "Approving refunds is left to the manager's discretion.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Nuance", "vocab_ipa": "/ˈnuːɑːns/", "vocab_meaning": "A subtle difference in meaning or expression.", "vocab_example": "The translator captured the nuance of the original text.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Subtlety", "vocab_ipa": "/ˈsʌtlti/", "vocab_meaning": "A fine or delicate distinction.", "vocab_example": "The negotiation required attention to subtlety and tone.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Connotation", "vocab_ipa": "/ˌkɑːnəˈteɪʃn/", "vocab_meaning": "An idea suggested by a word beyond its literal meaning.", "vocab_example": "The word \"cheap\" has a negative connotation.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Inference", "vocab_ipa": "/ˈɪnfərəns/", "vocab_meaning": "A conclusion reached through reasoning rather than direct statement.", "vocab_example": "Readers must draw an inference from the passage.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Presupposition", "vocab_ipa": "/ˌpriːsʌpəˈzɪʃn/", "vocab_meaning": "Something assumed to be true before an argument is made.", "vocab_example": "The proposal relies on a presupposition that costs will fall.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Tacit", "vocab_ipa": "/ˈtæsɪt/", "vocab_meaning": "Understood without being directly stated.", "vocab_example": "There was tacit agreement among the partners.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Implicit", "vocab_ipa": "/ɪmˈplɪsɪt/", "vocab_meaning": "Suggested without being directly expressed.", "vocab_example": "Trust was implicit in their long partnership.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Explicit", "vocab_ipa": "/ɪkˈsplɪsɪt/", "vocab_meaning": "Stated clearly and in detail.", "vocab_example": "The instructions were explicit about the deadline.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Prevailing", "vocab_ipa": "/prɪˈveɪlɪŋ/", "vocab_meaning": "Widely existing or accepted at a particular time.", "vocab_example": "The prevailing view is that rates will rise.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Pertinent", "vocab_ipa": "/ˈpɜːrtɪnənt/", "vocab_meaning": "Relevant to the matter at hand.", "vocab_example": "Please include only pertinent details in the summary.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Salient", "vocab_ipa": "/ˈseɪliənt/", "vocab_meaning": "Most noticeable or important.", "vocab_example": "The report highlights the salient risks of the plan.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Cogent", "vocab_ipa": "/ˈkoʊdʒənt/", "vocab_meaning": "Clear, logical, and convincing.", "vocab_example": "She presented a cogent argument for the merger.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Plausible", "vocab_ipa": "/ˈplɔːzəbl/", "vocab_meaning": "Reasonable or believable.", "vocab_example": "The explanation for the delay seemed plausible.", "vocab_cefr": "C2", "level": 14},
    {"vocab_word": "Tenable", "vocab_ipa": "/ˈtenəbl/", "vocab_meaning": "Able to be defended against objection.", "vocab_example": "Their position became less tenable after the audit.", "vocab_cefr": "C2", "level": 14},

    # --- Level 15 -- C2 -- idiomatic business English ------------------------------------
    {"vocab_word": "Touch base", "vocab_ipa": "", "vocab_meaning": "To make brief contact with someone.", "vocab_example": "Let's touch base again after the client call.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Ballpark figure", "vocab_ipa": "/ˈbɔːlpɑːrk ˈfɪɡjər/", "vocab_meaning": "A rough estimate.", "vocab_example": "Can you give me a ballpark figure for the project cost?", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Circle back", "vocab_ipa": "", "vocab_meaning": "To return to a topic or person later.", "vocab_example": "We'll circle back to pricing once the demo is done.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Low-hanging fruit", "vocab_ipa": "", "vocab_meaning": "Easy tasks or gains that require little effort.", "vocab_example": "Let's tackle the low-hanging fruit before the harder fixes.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Move the needle", "vocab_ipa": "", "vocab_meaning": "To make a noticeable difference or impact.", "vocab_example": "This campaign really moved the needle on sign-ups.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Think outside the box", "vocab_ipa": "", "vocab_meaning": "To think creatively, beyond usual limits.", "vocab_example": "The client wants us to think outside the box on this one.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "On the same page", "vocab_ipa": "", "vocab_meaning": "In agreement or sharing the same understanding.", "vocab_example": "Let's make sure everyone is on the same page before launch.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Bottom line", "vocab_ipa": "/ˈbɑːtəm laɪn/", "vocab_meaning": "The final, most important point, often financial.", "vocab_example": "The bottom line is that costs need to come down.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Game changer", "vocab_ipa": "", "vocab_meaning": "Something that significantly alters a situation.", "vocab_example": "The new partnership could be a real game changer.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Up in the air", "vocab_ipa": "", "vocab_meaning": "Undecided or uncertain.", "vocab_example": "The launch date is still up in the air.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Back burner", "vocab_ipa": "", "vocab_meaning": "Set aside as a low priority for now.", "vocab_example": "We put that proposal on the back burner for now.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Red tape", "vocab_ipa": "", "vocab_meaning": "Excessive official rules and procedures.", "vocab_example": "Getting approval took weeks because of red tape.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Rule of thumb", "vocab_ipa": "", "vocab_meaning": "A general, practical guideline.", "vocab_example": "As a rule of thumb, reply within 24 hours.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "In the loop", "vocab_ipa": "", "vocab_meaning": "Informed and included in communication.", "vocab_example": "Please keep me in the loop on any changes.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Across the board", "vocab_ipa": "", "vocab_meaning": "Applying equally to everyone or everything.", "vocab_example": "Salaries were increased across the board this year.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Par for the course", "vocab_ipa": "", "vocab_meaning": "Typical or expected, especially of something difficult.", "vocab_example": "Delays are par for the course during peak season.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "State of the art", "vocab_ipa": "", "vocab_meaning": "The most advanced and modern available.", "vocab_example": "Their factory uses state-of-the-art equipment.", "vocab_cefr": "C2", "level": 15},
    {"vocab_word": "Win-win", "vocab_ipa": "", "vocab_meaning": "An outcome that benefits everyone involved.", "vocab_example": "The revised deal turned out to be a win-win for both sides.", "vocab_cefr": "C2", "level": 15},
]


class Command(BaseCommand):
    help = "Replace the Vocabulary SkillLesson catalog with the full 15-level TOEIC set."

    @transaction.atomic
    def handle(self, *args, **options):
        vocabulary_skill = Skill.objects.filter(slug="vocabulary").first()
        if not vocabulary_skill:
            self.stderr.write(self.style.ERROR("Vocabulary skill not found — run seed_skills first."))
            return

        deleted, _ = SkillLesson.objects.filter(skill=vocabulary_skill).delete()
        self.stdout.write(f"Deleted {deleted} existing row(s) (SkillLesson + cascaded completions/review states).")

        created = 0
        used_slugs = set()
        for order, row in enumerate(VOCABULARY_LESSON_SEED, start=1):
            base_slug = slugify(row["vocab_word"])[:80]
            slug = base_slug
            suffix = 2
            while slug in used_slugs:
                slug = f"{base_slug[:76]}-{suffix}"
                suffix += 1
            used_slugs.add(slug)

            SkillLesson.objects.create(
                skill=vocabulary_skill,
                slug=slug,
                title=row["vocab_word"],
                sort_order=order,
                is_published=True,
                **{k: v for k, v in row.items() if k != "vocab_word"},
            )
            created += 1

        total = SkillLesson.objects.filter(skill=vocabulary_skill).count()
        self.stdout.write(self.style.SUCCESS(f"Vocabulary seed complete: {total} lesson(s), {created} created."))
