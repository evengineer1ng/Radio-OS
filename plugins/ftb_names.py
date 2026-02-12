"""
From The Backmarker - Human Name Generation System

Provides realistic human names for drivers, engineers, mechanics, strategists,
principals, and team names. All generation is deterministic based on seed.

Name pools designed for:
- Cultural diversity (European, Asian, American, Latin American, Middle Eastern)
- Gender representation (15% female drivers, 25% female engineers)
- Motorsport authenticity (real-world name patterns from F1/F2/IndyCar history)
"""

import hashlib
from typing import Tuple, Optional


# ============================================================================
# FIRST NAMES - MALE (1000+ names)
# ============================================================================
FIRST_NAMES_MALE = [
    # British/Irish
    "James", "Oliver", "George", "Harry", "Jack", "Charlie", "Thomas", "Oscar", "William", "Henry",
    "Liam", "Noah", "Ethan", "Lucas", "Mason", "Logan", "Alexander", "Max", "Benjamin", "Samuel",
    "Daniel", "Matthew", "Joseph", "David", "Andrew", "Ryan", "Connor", "Callum", "Lewis", "Jake",
    "Alfie", "Archie", "Jacob", "Joshua", "Sebastian", "Finley", "Arthur", "Theo", "Isaac", "Edward",
    "Harrison", "Toby", "Leo", "Dylan", "Freddie", "Adam", "Elliot", "Luke", "Nathan", "Owen",
    "Jamie", "Rory", "Kieran", "Declan", "Aidan", "Finn", "Patrick", "Sean", "Cillian", "Ronan",
    "Eoin", "Niall", "Brendan", "Lachlan",  "Fraser", "Angus", "Duncan", "Alistair", "Hamish", "Colin",
    "Graham", "Stuart", "Neil", "Ian", "Gordon", "Bruce", "Kenneth", "Douglas", "Malcolm", "Gavin",
    
    # Italian
    "Marco", "Luca", "Andrea", "Matteo", "Alessandro", "Lorenzo", "Francesco", "Giovanni", "Giulio", "Riccardo",
    "Stefano", "Paolo", "Antonio", "Davide", "Simone", "Nicola", "Gabriele", "Federico", "Filippo", "Leonardo",
    "Tommaso", "Samuele", "Pietro", "Emanuele", "Daniele", "Cristiano", "Michele", "Fabio", "Massimo", "Vincenzo",
    "Roberto", "Giuseppe", "Angelo", "Salvatore", "Sergio", "Mario", "Alberto", "Bruno", "Carlo", "Diego",
    "Edoardo", "Fabrizio", "Giacomo", "Ignazio", "Jacopo", "Liam", "Manuel", "Niccolo", "Ottavio", "Raffaele",
    "Salvatore", "Tommaso", "Umberto", "Valentino", "Vito", "Claudio", "Dario", "Elia", "Enrico", "Flavio",
    
    # Spanish/Latin American
    "Carlos", "Diego", "Javier", "Miguel", "Fernando", "Adrian", "Pablo", "Juan", "Luis", "Rafael",
    "Sergio", "Alejandro", "Manuel", "Pedro", "Raul", "Oscar", "Eduardo", "Felipe", "Emilio", "Santiago",
    "Mateo", "Sebastian", "Tomas", "Nicolas", "Gabriel", "Andres", "Ricardo", "Vicente", "Ignacio", "Joaquin",
    "Alberto", "Alvaro", "Antonio", "Arturo", "Benito", "Cesar", "Cristian", "Daniel", "David", "Enrique",
    "Esteban", "Facundo", "Francisco", "Gonzalo", "Guillermo", "Gustavo", "Hector", "Hugo", "Ivan", "Jaime",
    "Jorge", "Jose", "Leonardo", "Lorenzo", "Lucas", "Marco", "Mario", "Martin", "Mauricio", "Maximiliano",
    "Patricio", "Ramon", "Roberto", "Rodrigo", "Salvador", "Samuel", "Saul", "Teodoro", "Tiago", "Victor",
    "Xavier", "Yeremi", "Agustin", "Alonso", "Armando", "Bruno", "Dante", "Dario", "Elias", "Emanuel",
    
    # German/Austrian
    "Sebastian", "Max", "Michael", "Nico", "Mick", "Felix", "Lukas", "Jonas", "Leon", "Paul",
    "Tim", "Jan", "Marco", "Philipp", "Christian", "Andreas", "Tobias", "Stefan", "Daniel", "Thomas",
    "Alexander", "Benjamin", "David", "Elias", "Fabian", "Florian", "Jakob", "Julian", "Luca", "Maximilian",
    "Moritz", "Niklas", "Noah", "Oliver", "Samuel", "Simon", "Tom", "Valentin", "Wilhelm", "Anton",
    "Benedikt", "Carl", "Constantin", "Dominik", "Emil", "Erik", "Finn", "Gabriel", "Georg", "Gregor",
    "Gustav", "Hannes", "Heinrich", "Henry", "Ignaz", "Johannes", "Jonathan", "Josef", "Karl", "Konrad",
    "Lars", "Leopold", "Lorenz", "Luka", "Magnus", "Marius", "Markus", "Martin", "Matthias", "Nils",
    
    # French
    "Pierre", "Jean", "Luc", "Antoine", "Louis", "Alexandre", "Nicolas", "Julien", "Maxime", "Hugo",
    "Olivier", "Romain", "Sebastien", "Matthieu", "Francois", "Laurent", "Vincent", "Christophe", "Fabien", "Yann",
    "Arthur", "Baptiste", "Benoit", "Charles", "Clement", "Denis", "Didier", "Emile", "Emmanuel", "Eric",
    "Etienne", "Felix", "Florent", "Gabriel", "Guillaume", "Henri", "Jacques", "Jerome", "Jules", "Kevin",
    "Loic", "Marc", "Marcel", "Mathis", "Maurice", "Nathan", "Pascal", "Patrick", "Paul", "Philippe",
    "Quentin", "Raphael", "Rene", "Robert", "Samuel", "Simon", "Sylvain", "Theo", "Thibaut", "Thomas",
    "Valentin", "Victor", "Xavier", "Yves", "Adrien", "Alain", "Andre", "Arnaud", "Aymeric", "Bastien",
    
    # Scandinavian
    "Erik", "Lars", "Magnus", "Oscar", "Viktor", "Anders", "Nils", "Sven", "Henrik", "Johan",
    "Mikael", "Olaf", "Bjorn", "Axel", "Gustav", "Emil", "Linus", "Rasmus", "Thor", "Kimi",
    "Alexander", "Andreas", "Anton", "Carl", "Christian", "Daniel", "David", "Elias", "Filip", "Fredrik",
    "Gabriel", "Isak", "Jakob", "Jesper", "Jonas", "Karl", "Kristian", "Lucas", "Markus", "Martin",
    "Mats", "Mattias", "Niklas", "Oliver", "Oskar", "Patrik", "Per", "Peter", "Sebastian", "Simon",
    "Stefan", "Tobias", "Viggo", "Wilhelm", "Adrian", "Albin", "Alfred", "Arne", "Arvid", "Asbjorn",
    "Bengt", "Bo", "Dag", "Einar", "Eskil", "Felix", "Gunnar", "Haakon", "Hugo", "Ingvar",
    
    # Dutch/Belgian
    "Max", "Robin", "Tom", "Lars", "Luuk", "Daan", "Bram", "Thijs", "Jasper", "Ruben",
    "Niels", "Sander", "Jeroen", "Martijn", "Pieter", "Stijn", "Yannick", "Kevin", "Stoffel", "Vandoorne",
    "Alexander", "Bas", "Bart", "Benjamin", "Casper", "Christiaan", "David", "Dennis", "Diederik", "Erik",
    "Floris", "Frank", "Gijs", "Guus", "Henk", "Jesse", "Joost", "Joren", "Julian", "Koen",
    "Laurens", "Leon", "Levi", "Maarten", "Matthijs", "Milan", "Nick", "Noah", "Olivier", "Pascal",
    "Patrick", "Paul", "Peter", "Rens", "Rick", "Roy", "Sam", "Sebastian", "Simon", "Stefan",
    "Sven", "Teun", "Thomas", "Tim", "Timo", "Tobias", "Victor", "Wessel", "Willem", "Wouter",
    
    # Eastern European
    "Nikita", "Sergey", "Daniil", "Artem", "Mikhail", "Alexei", "Vitaly", "Robert", "Kamil", "Jakub",
    "Milos", "Luka", "Ivan", "Andrei", "Dmitry", "Pavel", "Anton", "Yuri", "Vladimir", "Stanislav",
    "Alexander", "Alexey", "Anatoly", "Andrej", "Bogdan", "Boris", "Constantin", "Denis", "Dimitri", "Evgeny",
    "Fedor", "Georgi", "Grigory", "Igor", "Ilya", "Jan", "Jaroslav", "Kirill", "Konstantin", "Krzysztof",
    "Ladislav", "Lech", "Leonid", "Marek", "Marian", "Mateusz", "Maxim", "Milan", "Miroslav", "Nikola",
    "Oleg", "Petr", "Piotr", "Radek", "Roman", "Sasha", "Stefan", "Tomas", "Vadim", "Valentin",
    "Vaclav", "Viktor", "Vojtech", "Yaroslav", "Yegor", "Zakhar", "Zbigniew", "Zdenek", "Aleksandar", "Branko",
    
    # Japanese
    "Takuma", "Yuki", "Naoki", "Ryo", "Hiroshi", "Kenta", "Daiki", "Kenji", "Satoru", "Yuji",
    "Nobuharu", "Kamui", "Kazuki", "Tatsuya", "Shinji", "Takeshi", "Ryota", "Makoto", "Akira", "Haruki",
    "Kaito", "Haruto", "Sota", "Yuuto", "Hayato", "Ren", "Kouki", "Shota", "Daichi", "Tomoya",
    "Shun", "Tsubasa", "Taiga", "Ryuusei", "Yuuma", "Takuya", "Shou", "Yamato", "Ayumu", "Kouhei",
    "Masato", "Takeru", "Ryousuke", "Kaoru", "Keita", "Shouta", "Takahiro", "Daisuke", "Kento", "Shingo",
    "Taro", "Jiro", "Hikaru", "Isamu", "Jun", "Masaru", "Minoru", "Osamu", "Ryuu", "Susumu",
    "Tadashi", "Takao", "Teruo", "Toshio", "Yasuo", "Yoshio", "Ichiro", "Saburo", "Shiro", "Goro",
    
    # Chinese
    "Wei", "Guanyu", "Zhen", "Ming", "Chen", "Jun", "Hao", "Yang", "Feng", "Liang",
    "Zhou", "Ma", "Ye", "Guo", "Zhu", "Yifei", "Chenyi", "Kaiyi", "Muyang", "Zijian",
    "Wei", "Jie", "Han", "Lei", "Tao", "Xin", "Yu", "Kai", "Long", "Peng",
    "Qiang", "Rui", "Tian", "Xiang", "Yong", "Zhong", "Bo", "Chao", "Dong", "Gang",
    "Hui", "Jian", "Kun", "Lin", "Ming", "Ning", "Qing", "Shan", "Tong", "Wen",
    "Xiao", "Yi", "Ze", "An", "Bao", "Cai", "De", "En", "Fu", "Guan",
    "Hong", "Jin", "Kang", "Li", "Meng", "Nian", "Ou", "Ping", "Qiu", "Ren",
    
    # Brazilian
    "Felipe", "Bruno", "Lucas", "Gabriel", "Helio", "Nelson", "Rubens", "Ayrton", "Emerson", "Jose",
    "Pietro", "Enzo", "Thiago", "Matheus", "Vinicius", "Gustavo", "Rafael", "Rodrigo", "Marcelo", "Leonardo",
    "Arthur", "Bernardo", "Davi", "Guilherme", "Henrique", "Igor", "Joao", "Caio", "Daniel", "Eduardo",
    "Fernando", "Fabricio", "Giovanni", "Hugo", "Iago", "Isaac", "Kaique", "Lorenzo", "Murilo",  "Nicolas",
    "Otavio", "Paulo", "Pedro", "Raul", "Renan", "Samuel", "Theo", "Victor", "Vitor", "Yuri",
    "Alexandre", "Andre", "Carlos", "Diego", "Fabio", "Flavio", "Giovani", "Heitor", "Julio", "Leandro",
    "Luis", "Marcos", "Miguel", "Nathan", "Cesar", "Ricardo", "Roberto", "Sergio", "Washington", "Lucca",
    
    # American/Canadian
    "Tyler", "Brandon", "Justin", "Austin", "Kyle", "Chase", "Colton", "Blake", "Connor", "Ryan",
    "Hunter", "Logan", "Cole", "Mason", "Ethan", "Jackson", "Dylan", "Zach", "Scott", "Alexander",
    "Nicholas", "Josef", "Will", "Graham", "Parker", "Reid", "Dalton", "Conor", "Santino", "Pato",
    "Aaron", "Adam", "Adrian", "Andrew", "Anthony", "Benjamin", "Bradley", "Brian", "Caleb", "Cameron",
    "Carter", "Charles", "Christian", "Christopher", "Cody", "Cooper", "Damian", "Derek", "Dominic", "Eli",
    "Elijah", "Eric", "Evan", "Gavin", "Grant", "Ian", "Isaac", "Jack", "Jacob", "James",
    "Jason", "Jayden", "Jesse", "Joel", "Jordan", "Joshua", "Julian", "Kevin", "Landon", "Levi",
    "Liam", "Lucas", "Luke", "Marcus", "Mark", "Matthew", "Michael", "Nathan", "Noah", "Owen",
    
    # Australian/NZ
    "Daniel", "Jack", "Mark", "Oscar", "Liam", "Mitchell", "Nick", "Will", "Thomas", "James",
    "Matthew", "Scott", "Brett", "Shane", "Craig", "Cameron", "Luke", "Ryan", "Brendon", "Marcus",
    "Alexander", "Benjamin", "Callum", "Cooper", "Dylan", "Ethan", "Harrison", "Isaac", "Jackson", "Joshua",
    "Kyle", "Lewis", "Mason", "Nathan", "Noah", "Oliver", "Patrick", "Riley", "Samuel", "Sebastian",
    "Tyler", "William", "Xavier", "Zachary", "Adam", "Blake", "Connor", "Declan", "Finn", "George",
    "Harry", "Jayden", "Kai", "Logan", "Max", "Angus", "Hamish", "Archie", "Charlie", "Hudson",
    "Hunter", "Bailey", "Jordan", "Flynn", "Archer", "Ashton", "Austin", "Beau", "Brady", "Carter",
    
    # Indian/South Asian
    "Arjun", "Rohan", "Karthik", "Aditya", "Raj", "Vikram", "Nikhil", "Rahul", "Siddharth", "Aarav",
    "Armaan", "Daruvala", "Karun", "Narain", "Jehan", "Yuven", "Advait", "Ishan", "Rehan", "Kunal",
    "Aadhav", "Abhay", "Abhishek", "Akash", "Aman", "Amit", "Anand", "Aniket", "Anish", "Ankur",
    "Aryan", "Ashwin", "Ayaan", "Ayush", "Chirag", "Daksh", "Deepak", "Dev", "Dhruv", "Gaurav",
    "Hardik", "Harsh", "Jay", "Karan", "Keshav", "Krishna", "Manish", "Mohit", "Neel", "Parth",
    "Pranav", "Pratik", "Rishi", "Ritesh", "Sahil", "Sameer", "Samir", "Shaan", "Shaurya", "Shiv",
    "Shreyas", "Tanay", "Tanmay", "Varun", "Ved", "Vihaan", "Viraj", "Yash", "Arnav", "Ishaan",
    
    # Middle Eastern
    "Omar", "Khalil", "Mohammed", "Rashid", "Tariq", "Saif", "Karim", "Faisal", "Youssef", "Hassan",
    "Abdullah", "Ahmed", "Ali", "Amir", "Bilal", "Fahad", "Hamza", "Ibrahim", "Jamal", "Kareem",
    "Malik", "Mustafa", "Nasser", "Naveed", "Qasim", "Rafiq", "Salman", "Sami", "Tahir", "Waleed",
    "Yasin", "Younis", "Zain", "Zaki", "Adil", "Asad", "Basel", "Basil", "Daud", "Ehsan",
    "Emir", "Farid", "Ghazi", "Habib", "Hakim", "Hamed", "Hashim", "Imran", "Ismail", "Jalal",
    "Jamil", "Jawad", "Kamil", "Latif", "Mazen", "Nabil", "Nadim", "Nasir", "Rami", "Rayan",
    
    # African
    "Zane", "Kaylen", "Jordan", "Connor", "Tyler", "Kelvin", "Jonathan", "Stephen", "Nicholas", "Michael",
    "Thabiso", "Lwazi", "Sipho", "Thabo", "Mandla", "Bongani", "Sizwe", "Nkosi", "Mpho", "Kagiso",
    "Kwame", "Kofi", "Kwesi", "Kojo", "Yaw", "Kwaku", "Emmanuel", "Joseph", "Benjamin", "Samuel",
    "Tendai", "Tatenda", "Tinashe", "Tafara", "Takudzwa", "Brian", "Keith", "Adrian", "Ryan", "Brandon",
    "Jabu", "Musa", "Simphiwe", "Siyabonga", "Sabelo", "Mohamed", "Ahmed", "Youssef", "Karim", "Omar",
    "Chinedu", "Obinna", "Emeka", "Chidera", "Chukwudi", "Nnamdi", "Ike", "Eze", "Kelechi", "Uchenna",
    
    # Korean
    "Min-Seok", "Ji-Ho", "Tae-Yang", "Joon-Woo", "Sung-Min", "Hyun-Woo", "Jin-Woo", "Seo-Jun", "Jae-Sung", "Dong-Hyun",
    "Young-Ho", "Kyung-Min", "Sang-Hoon", "Chang-Min", "Jae-Won", "Seung-Ho", "Min-Ho", "Jun-Seo", "Woo-Jin", "Yoon-Seok",
    "Byung-Hun", "Dae-Jung", "Gi-Tae", "Ho-Sung", "In-Sung", "Jung-Hoon", "Kang-Min", "Nam-Joon", "Sang-Woo", "Tae-Min",
    "Won-Shik", "Yong-Soo", "Chul-Soo", "Hae-Sung", "Joon-Ho", "Ki-Joon", "Min-Jae", "Seok-Jin", "Tae-Hyung", "Woo-Sung",
    "Yeon-Joon", "Beom-Seok", "Dong-Wook", "Hee-Chan", "Jae-Min", "Kyu-Hyun", "Myung-Soo", "Sang-Hyun", "Tae-Woo", "Yoo-Jin",
    "Kwang-Soo", "Dae-Hyun", "Jin-Young", "Young-Jae", "Sung-Hoon", "Jae-Hyun", "Min-Soo", "Tae-Jun", "Woo-Hyun", "Yoo-Seok",
    
    # Southeast Asian
    "Preecha", "Somchai", "Sutin", "Ananda", "Tawan", "Chalerm", "Niran", "Kittipat", "Danial", "Hafiz",
    "Arif", "Rizal", "Faizal", "Amin", "Zainal", "Iskandar", "Ahmad", "Hakim", "Syafiq", "Azman",
    "Joko", "Budi", "Agus", "Eko", "Hadi", "Rudi", "Yudi", "Andi", "Dedi", "Firman",
    "Jose", "Miguel", "Carlo", "Rafael", "Antonio", "Ramon", "Juan", "Pedro", "Luis", "Mario",
    "Thanh", "Minh", "Tuan", "Duc", "Huy", "Long", "Nam", "Phong", "Quang", "Truong",
    "Aung", "Kyaw", "Min", "Thant", "Win", "Zaw", "Htet", "Naing", "Phyo", "Thiha",
    "Somchai", "Wattana", "Prasert", "Sombat", "Surasak", "Chaiyong", "Narong", "Somsak", "Thawat", "Boonsong",
    
    # Additional unique motorsport names
    "Maro", "Nyck", "Jean-Eric", "Rene", "Esteban", "Pascal", "Jolyon", "Rio", "Guanyu", "Lance",
    "Jenson", "Jarno", "Giancarlo", "Timo", "Heikki", "Vitantonio", "Adrian", "Mark", "Rubens", "Giedo",
    "Stoffel", "Marcus", "Kevin", "Romain", "Nico", "Felipe", "Daniil", "Pierre", "Charles", "Lando",
    "George", "Carlos", "Sergio", "Valtteri", "Kimi", "Fernando", "Lewis", "Max", "Daniel", "Mick"
]

# ============================================================================
# FIRST NAMES - FEMALE (1000+ names)
# ============================================================================
FIRST_NAMES_FEMALE = [
    # British/Irish
    "Emma", "Olivia", "Sophia", "Ava", "Isabella", "Charlotte", "Amelia", "Emily", "Mia", "Harper",
    "Ella", "Grace", "Lily", "Sophie", "Chloe", "Lucy", "Jessica", "Ruby", "Freya", "Evie",
    "Alice", "Florence", "Phoebe", "Rose", "Daisy", "Isla", "Poppy", "Zara", "Pippa", "Jess",
    "Scarlett", "Isabelle", "Aria", "Ellie", "Millie", "Sienna", "Layla", "Matilda", "Maya", "Eva",
    "Hannah", "Violet", "Ivy", "Bella", "Georgia", "Rosie", "Molly", "Abigail", "Holly", "Evelyn",
    "Eleanor", "Eliza", "Imogen", "Elizabeth", "Willow", "Jasmine", "Victoria", "Madison", "Katie", "Paige",
    "Niamh", "Aoife", "Ciara", "Siobhan", "Aisling", "Orla", "Roisin", "Clodagh", "Maeve", "Caoimhe",
    "Fiona", "Sinead", "Mairead", "Aoibhe", "Saoirse", "Leah", "Sarah", "Rachel", "Lauren", "Rebecca",
    
    # Italian
    "Sofia", "Giulia", "Francesca", "Chiara", "Sara", "Martina", "Giorgia", "Alessia", "Elena", "Anna",
    "Valentina", "Elisa", "Federica", "Beatrice", "Camilla", "Aurora", "Gaia", "Vittoria", "Ginevra", "Bianca",
    "Alice", "Emma", "Giada", "Matilde", "Viola", "Nicole", "Arianna", "Noemi", "Caterina", "Rebecca",
    "Ludovica", "Martina", "Carlotta", "Benedetta", "Eleonora", "Greta", "Chiara",  "Cecilia", "Diana", "Flaminia",
    "Giovanna", "Ilaria", "Laura", "Lucia", "Maria", "Margherita", "Monica", "Paola", "Roberta", "Serena",
    "Silvia", "Simona", "Stefania", "Teresa", "Veronica", "Alessandra", "Angela", "Antonella", "Barbara", "Claudia",
    
    # Spanish/Latin American
    "Maria", "Carmen", "Isabel", "Ana", "Laura", "Paula", "Lucia", "Sofia", "Elena", "Marta",
    "Clara", "Alba", "Valeria", "Daniela", "Alejandra", "Carolina", "Gabriela", "Natalia", "Andrea", "Victoria",
    "Camila", "Valentina", "Isabella", "Catalina", "Fernanda", "Mariana", "Adriana", "Julieta", "Renata", "Ximena",
    "Beatriz", "Carla", "Claudia", "Cristina", "Diana", "Emilia", "Estefania", "Eva", "Florencia", "Gloria",
    "Irene", "Julia", "Lola", "Lorena", "Luisa", "Manuela", "Marina", "Mercedes", "Monica", "Noelia",
    "Nuria", "Olivia", "Patricia", "Pilar", "Raquel", "Rosa", "Rosario", "Silvia", "Tatiana", "Teresa",
    "Veronica", "Yolanda", "Azucena", "Belen", "Dolores", "Encarna", "Francisca", "Guadalupe", "Helena", "Inmaculada",
    "Josefina", "Leticia", "Magdalena", "Marisol", "Milagros", "Montserrat", "Paloma", "Rocio", "Soledad", "Susana",
    
    # German/Austrian
    "Sophie", "Marie", "Lena", "Anna", "Laura", "Emma", "Lea", "Hannah", "Sarah", "Julia",
    "Lisa", "Mia", "Katharina", "Nina", "Paula", "Amelie", "Charlotte", "Emilia", "Johanna", "Luisa",
    "Clara", "Elena", "Frieda", "Greta", "Helena", "ida", "Jana", "Klara", "Lara", "Maria",
    "Marlene", "Mathilda", "Nele", "Nora", "Olivia", "Rosa", "Sophia", "Theresa", "Valentina", "Zoe",
    "Annika", "Antonia", "Caroline", "Christina", "Diana", "Elisabeth", "Franziska", "Gerda", "Hanna", "Helga",
    "Ingrid", "Isabella", "Jasmin", "Karla", "Laura", "Magdalena", "Martina", "Melanie", "Monika", "Natalie",
    "Nicole", "Petra", "Rebecca", "Regina", "Sabine", "Sandra", "Silke", "Stefanie", "Susanne", "Ursula",
    
    # French
    "Marie", "Camille", "Lea", "Emma", "Chloe", "Sophie", "Julie", "Clara", "Alice", "Manon",
    "Amelie", "Juliette", "Sarah", "Laura", "Jade", "Louise", "Charlotte", "Pauline", "Elise", "Marine",
    "Anais", "Aurelie", "Axelle", "Celine", "Clemence", "Diane", "Eloise", "Estelle", "Eva", "Florence",
    "Gabrielle", "Helene", "Ines", "Jeanne", "Justine", "Laure", "Lena", "Lise", "Lucie", "Margaux",
    "Mathilde", "Noemie", "Oceane", "Zoe", "Adele", "Agathe", "Anne", "Beatrice", "Caroline", "Catherine",
    "Claire", "Delphine", "Emilie", "Elodie", "Fanny", "Geraldine", "Isabelle", "Laetitia", "Maeva", "Margot",
    "Melanie", "Mireille", "Morgane", "Nathalie", "Nicole", "Olivia", "Patricia", "Sandrine", "Stephanie", "Sylvie",
    
    # Scandinavian
    "Emma", "Maja", "Olivia", "Alice", "Julia", "Linnea", "Ella", "Saga", "Wilma", "Ebba",
    "Astrid", "Elsa", "Ingrid", "Frida", "Signe", "Liv", "Sofia", "Mia", "Luna", "Nova",
    "Alva", "Alma", "Asta", "Elise", "Emilie", "Ester", "Freja", "Hanna", "Ida", "Iris",
    "Klara", "Lea", "Lilly", "Lova", "Molly", "Nora", "Sara", "Selma", "Sigrid", "Stella",
    "Vera", "Agnes", "Alma", "Annika", "Birgit", "Britta", "Carolina", "Charlotte", "Cristina", "Ellen",
    "Emelie", "Helena", "Johanna", "Josefin", "Karin", "Katarina", "Lisa", "Malin", "Maria", "Matilda",
    "Rebecka", "Sandra", "Susanna", "Therese", "Viktoria", "Anna", "Cecilia", "Erika", "Gunilla", "Margareta",
    
    # Dutch/Belgian
    "Emma", "Sophie", "Julia", "Lisa", "Lotte", "Anna", "Eva", "Fleur", "Nina", "Sara",
    "Anouk", "Liv", "Femke", "Roos", "Iris", "Luna", "Noor", "Mila", "Sanne", "Amber",
    "Anne", "Britt", "Demi", "Eline", "Fenna", "Jasmijn", "Lauren", "Lieke", "Maud", "Naomi",
    "Noa", "Olivia", "Romy", "Sofie", "Tess", "Vera", "Amber", "Charlotte", "Diane", "Elena",
    "Elise", "Emily", "Esther", "Hanna", "Jill", "Julie", "Kim", "Laura", "Lena", "Lynn",
    "Maria", "Merel", "Michelle", "Mirthe", "Nienke", "Rebecca", "Robin", "Saar", "Sophia", "Tamara",
    "Vanessa", "Yasmin", "Zoë", "Anke", "Carlijn", "Danique", "Esmee", "Floor", "Ilse", "Janna",
    
    # Eastern European
    "Anastasia", "Ekaterina", "Maria", "Anna", "Daria", "Viktoria", "Alexandra", "Sofia", "Elena", "Natalia",
    "Olga", "Yulia", "Svetlana", "Irina", "Tatiana", "Oksana", "Alina", "Polina", "Arina", "Varvara",
    "Alisa", "Angelina", "Diana", "Eva", "Galina", "Inna", "Kira", "Kristina", "Larisa", "Ludmila",
    "Marina", "Nadezhda", "Nina", "Oxana", "Raisa", "Tamara", "Valentina", "Vera", "Veronika", "Vlada",
    "Yana", "Zoya", "Agnieszka", "Aleksandra", "Alicja", "Barbara", "Beata", "Dagmara", "Dominika", "Dorota",
    "Elzbieta", "Ewa", "Gabriela", "Hanna", "Iwona", "Joanna", "Julia", "Justyna", "Karolina", "Katarzyna",
    "Magdalena", "Malgorzata", "Monika", "Natalia", "Oliwia", "Paulina", "Sylwia", "Urszula", "Weronika", "Zuzanna",
    
    # Japanese
    "Yuki", "Sakura", "Hana", "Aiko", "Rei", "Haruka", "Miku", "Ayumi", "Natsuki", "Rina",
    "Akari", "Hinata", "Yui", "Mai", "Kana", "Sora", "Miyu", "Nanami", "Riko", "Mio",
    "Airi", "Asuka", "Chiaki", "Erika", "Haru", "Hikari", "Honoka", "Kaori", "Kasumi", "Kiko",
    "Koharu", "Kumiko", "Maki", "Mami", "Manami", "Mariko", "Mayumi", "Megumi", "Michiko", "Midori",
    "Mihoko", "Minako", "Misaki", "Mizuki", "Momoka", "Naoko", "Nao", "Naomi", "Nori", "Noriko",
    "Riko", "Rie", "Risa", "Ryoko", "Sachiko", "Saori", "Sayaka", "Sayuri", "Shiori", "Sumiko",
    "Tomoe", "Tomoko", "Yoko", "Yoshiko", "Yuka", "Yukari", "Yukiko", "Yumi", "Yumiko", "Yuriko",
    
    # Chinese
    "Li", "Wei", "Mei", "Jing", "Ying", "Xia", "Ming", "Hua", "Yan", "Fang",
    "Lin", "Yue", "Xiu", "Qing", "Zhen", "Ling", "Shu", "Yu", "Chen", "Rong",
    "Ai", "An", "Bei", "Bao", "Chun", "Dan", "Fei", "Gui", "Hong", "Hui",
    "Jia", "Jin", "Juan", "Jun", "Lan", "Lei", "Lian", "Lily", "Ling", "Luan",
    "Meng", "Min", "Na", "Ning", "Nuan", "Ping", "Qian", "Qiu", "Rou", "Ru",
    "Shan", "Shao", "Shuang", "Tao", "Ting", "Wan", "Wen", "Xian", "Xiao", "Xin",
    "Xing", "Xu", "Ya", "Yi", "Yun", "Zhi", "Zhou", "Zhu", "Zi", "Zoe",
    
    # Brazilian
    "Ana", "Beatriz", "Julia", "Larissa", "Fernanda", "Gabriela", "Camila", "Mariana", "Isabella", "Carolina",
    "Rafaela", "Bianca", "Amanda", "Leticia", "Vitoria", "Sophia", "Laura", "Marina", "Marcela", "Bruna",
    "Alice", "Alicia", "Aline", "Andreia", "Angelica", "Barbara", "Carla", "Claudia", "Cristina", "Daniela",
    "Debora", "Eduarda", "Elaine", "Erica", "Fabiana", "Flavia", "Giovana", "Gisele", "Heloisa", "Helena",
    "Ingrid", "Isabela", "Jaqueline", "Jessica", "Joana", "Joyce", "Juliana", "Karla", "Karina", "Kelly",
    "Lara", "Livia", "Lorena", "Luciana", "Luisa", "Marcia", "Maria", "Michele", "Monica", "Natalia",
    "Patricia", "Paula", "Priscila", "Renata", "Rita", "Roberta", "Sandra", "Sara", "Silvia", "Simone",
    
    # American/Canadian
    "Sarah", "Ashley", "Madison", "Samantha", "Taylor", "Rachel", "Hannah", "Alexis", "Nicole", "Jessica",
    "Elizabeth", "Lauren", "Emma", "Grace", "Abigail", "Natalie", "Chloe", "Victoria", "Haley", "Morgan",
    "Ava", "Brooklyn", "Kennedy", "Peyton", "Riley", "Quinn", "Skylar", "Reagan", "Piper", "Kendall",
    "Addison", "Alexandra", "Allison", "Alyssa", "Amanda", "Amber", "Amy", "Andrea", "Angela", "Anna",
    "Ariana", "Audrey", "Bailey", "Bethany", "Brianna", "Brittany", "Caroline", "Cassidy", "Catherine", "Christina",
    "Claire", "Danielle", "Destiny", "Diana", "Eleanor", "Elena", "Emily", "Erin", "Gabriella", "Gianna",
    "Hailey", "Harper", "Heather", "Isabella", "Jasmine", "Jennifer", "Julia", "Kayla", "Kelly", "Kimberly",
    "Kylie", "Leah", "Lily", "Lindsay", "Mackenzie", "Madeline", "Megan", "Melanie", "Melissa", "Michelle",
    
    # Australian/NZ
    "Charlotte", "Olivia", "Amelia", "Isla", "Mia", "Grace", "Ruby", "Sophie", "Emily", "Chloe",
    "Lily", "Ava", "Zoe", "Isabella", "Emma", "Harper", "Poppy", "Ella", "Jessica", "Lucy",
    "Abigail", "Alice", "Annabelle", "Aria", "Bella", "Caitlin", "Claire", "Eloise", "Eva", "Evelyn",
    "Georgia", "Hannah", "Holly", "Imogen", "Ivy", "Jade", "Jasmine", "Kayla", "Layla", "Leah",
    "Lillian", "Mackenzie", "Madison", "Matilda", "Maya", "Megan", "Natalie", "Paige", "Phoebe", "Rosie",
    "Sadie", "Sarah", "Scarlett", "Sienna", "Sophia", "Stella", "Summer", "Violet", "Willow", "Zara",
    "Alyssa", "Amy", "Anna", "Ashley", "Bethany", "Bianca", "Brooke", "Chelsea", "Courtney", "Eliza",
    
    # Indian/South Asian
    "Priya", "Ananya", "Isha", "Kavya", "Diya", "Sanya", "Aaradhya", "Myra", "Sara", "Anika",
    "Riya", "Sneha", "Tara", "Kiara", "Naina", "Saanvi", "Avani", "Navya", "Meera", "Zara",
    "Aanya", "Aditi", "Ahana", "Aisha", "Anjali", "Anvi", "Aradhya", "Arya", "Avika", "Bhavya",
    "Deepika", "Divya", "Ishita", "Janvi", "Jiya", "Khushi", "Lavanya", "Mahika", "Mira", "Nidhi",
    "Nikita", "Nimra", "Palak", "Pari", "Pihu", "Pooja", "Preeti", "Radhika", "Rhea", "Riddhi",
    "Sakshi", "Samira", "Sanaya", "Sanika", "Sanjana", "Shanaya", "Shreya", "Simran", "Tanvi", "Trisha",
    "Vanya", "Vedika", "Vidya", "Zoya", "Aadhya", "Aanya", "Alisha", "Amara", "Anushka", "Arushi",
    
    # Middle Eastern
    "Layla", "Amira", "Sara", "Noor", "Zara", "Yasmin", "Leila", "Fatima", "Aisha", "Maryam",
    "Aaliyah", "Amina", "Dina", "Hana", "Jana", "Lina", "Malak", "Nadia", "Nour", "Rania",
    "Reem", "Salma", "Samira", "Soraya", "Zahra", "Zainab", "Abeer", "Alya", "Arwa", "Basma",
    "Dalal", "Farah", "Ghada", "Hala", "Huda", "Iman", "Karima", "Lamia", "Mariam", "Maysa",
    "Nabila", "Naima", "Noura", "Rasha", "Rima", "Safia", "Sahar", "Samia", "Suha", "Wafa",
    "Yara", "Zeina", "Aziza", "Bushra", "Dalia", "Fatma", "Habiba", "Haneen", "Inaya", "Jumana",
    
    # African
    "Zara", "Aaliyah", "Amara", "Nia", "Zuri", "Imani", "Safiya", "Kira", "Lila", "Maya",
    "Amahle", "Thandiwe", "Zola", "Nala", "Kefilwe", "Lerato", "Naledi", "Palesa", "Refilwe", "Thato",
    "Abeni", "Adama", "Amina", "Asha", "Ayanna", "Chiamaka", "Chioma", "Ebele", "Eshe", "Fatoumata",
    "Halima", "Ifunanya", "Khadija", "Makena", "Mariama", "Naima", "Nneka", "Nkechi", "Precious", "Salamatu",
    "Simisola", "Taiye", "Temitope", "Yetunde", "Zainab", "Akosua", "Ama", "Efua", "Esi", "Adjoa",
    "Michelle", "Nicole", "Rebecca", "Sarah", "Kimberly", "Natasha", "Candice", "Charlene", "Danielle", "Lauren",
    
    # Korean
    "Min-Ji", "Seo-Yun", "Ji-Woo", "Ha-Yoon", "Seo-Hyun", "Yu-Jin", "Ji-Yeon", "Mi-Na", "Su-Jin", "Hye-Jin",
    "Young-Hee", "Eun-Ji", "Soo-Min", "Ji-Hye", "Min-Jung", "Hye-Won", "Yeon-Soo", "Mi-Kyung", "Sun-Hee", "Ji-Soo",
    "Kyung-Mi", "Jin-A", "Hye-Sook", "Sung-Hee", "Mi-Sook", "In-Sook", "Eun-Young", "Seon-Hee", "Hee-Ra", "Bo-Young",
    "So-Hyun", "Joo-Hee", "Ye-Eun", "Da-Eun", "Ha-Eun", "Hae-Won", "Sung-Yeon", "Mi-Sun", "Jung-Eun", "Hye-Kyung",
    "Soo-Young", "Min-Ah", "Ji-Sun", "Young-Mi", "Eun-Hee", "Hyun-Jung", "Na-Young", "Yoo-Jung", "Ji-Eun", "Hee-Kyung",
    "Seo-Jin", "Ye-Jin", "Se-Young", "So-Yeon", "Hye-Rim", "Min-Kyung", "Ji-Young", "Yeon-Ji", "Hee-Sun", "Mi-Young",
    
    # Southeast Asian
    "Mali", "Siti", "Areeya", "Siriporn", "Kulap", "Niran", "Porn", "Suda", "Waranya", "Yuppa",
    "Aisyah", "Fatimah", "Nur", "Siti", "Aishah", "Zainab", "Khadijah", "Mariam", "Azura", "Nadia",
    "Dewi", "Sari", "Indah", "Puteri", "Rani", "Wati", "Wulan", "Kartika", "Lestari", "Mega",
    "Maria", "Rosa", "Angela", "Sofia", "Isabel", "Carmen", "Ana", "Luz", "Teresa", "Patricia",
    "Linh", "Mai", "Thi", "Huong", "Lan", "Thuy", "Nga", "Phuong", "Hong", "Tuyet",
    "Suu", "Kyi", "Mya", "Nwe", "Htet", "Aye", "Thiri", "Hlaing", "Moe", "Htun",
    "Sumalee", "Pranee", "Siriwan", "Nittaya", "Vilai", "Somsri", "Chutima", "Sasithorn", "Wipaporn", "Kanya",
    
    # Additional unique motorsport names
    "Jamie", "Chadwick", "Tatiana", "Calderon", "Simona", "De Silvestro", "Katherine", "Legge", "Pippa", "Mann",
    "Susie", "Wolff", "Maria", "Teresa", "Danica", "Patrick", "Desire", "Wilson", "Sophia", "Floersch",
    "Beitske", "Visser", "Sarah", "Fisher", "Milka", "Duno", "Ana", "Beatriz", "Divina", "Galica",
    "Giovanna", "Amati", "Lella", "Lombardi", "Desiré", "Michela", "Cerruti", "Bianca", "Bustamante", "Abbi", "Pulling"
]

# ============================================================================
# SURNAMES (1500+ names)
# ============================================================================
SURNAMES = [

    # ======================================================================
    # BRITISH / IRISH (230 names)
    # ======================================================================
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson",
    "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin",
    "Thompson", "Robinson", "Clark", "Lewis", "Lee", "Walker", "Hall", "Allen",
    "Young", "King", "Wright", "Hill", "Scott", "Green", "Adams", "Baker", "Nelson",
    "Carter", "Mitchell", "Roberts", "Turner", "Phillips", "Campbell", "Parker",
    "Evans", "Edwards", "Collins", "Stewart", "Morris", "Rogers", "Reed", "Cook",
    "Morgan", "Bell", "Murphy", "Bailey", "Cooper", "Richardson", "Cox", "Howard",
    "Ward", "Bennett", "Wood", "Clarke", "Foster", "Reynolds", "Marshall", "Price",
    "Coleman", "Pearson", "Brooks", "Matthews",
    
    # Additional British/Irish surnames
    "Hughes", "Gray", "James", "Watson", "Brooks", "Kelly", "Sanders", "Price", "Russell", "Griffin",
    "Dixon", "Hayes", "Myers", "Ford", "Hamilton", "Graham", "Sullivan", "Wallace", "Woods", "Cole",
    "West", "Jordan", "Owens", "Reynolds", "Fisher", "Ellis", "Harrison", "Gibson", "McDonald", "Cruz",
    "Marshall", "Ortiz", "Gomez", "Murray", "Freeman", "Wells", "Webb", "Simpson", "Stevens", "Tucker",
    "Porter", "Hunter", "Hicks", "Crawford", "Henry", "Boyd", "Mason", "Morales", "Kennedy", "Warren",
    "Dixon", "Ramos", "Reyes", "Palmer", "Lowe", "Barker", "Jennings", "Barnett", "Graves", "Jimenez",
    "Horton", "Shelton", "Barrett", "O'Brien", "Castro", "Sutton", "Gregory", "McKinney", "Lucas", "Miles",
    "Craig", "Lawson", "Chambers", "Holt", "Lambert", "Fletcher", "Watts", "Barclay", "Brennan", "Logan",
    "Burke", "Kennedy", "Lynch", "O'Connor", "O'Sullivan", "Walsh", "McCarthy", "Gallagher", "O'Neill", "Quinn",
    "Ryan", "Doyle", "Murray", "Doherty", "Kennedy", "Lynch", "Byrne", "Brennan", "Donnelly", "Duffy",
    "Bradley", "Flynn", "Ferguson", "Cunningham", "Shaw", "Henderson", "Robertson", "MacLeod", "MacDonald", "Fraser",
    "Grant", "Sutherland", "Duncan", "Cameron", "Ross", "Sinclair", "MacKenzie", "Gordon", "Stewart", "Murray",
    "Reid", "Wallace", "Burns", "MacKay", "Miller", "Thomson", "Wilson", "Hughes", "Johnston", "Wright",
    "Paterson", "Blair", "Gibson", "Kelly", "McDonald", "Morrison", "Ferguson", "Jenkins", "Owen", "Spencer",  
    "Webb", "Chapman", "Richards", "Harrison", "Gardner", "Palmer", "Shaw", "Elliott", "Sullivan", "Perry",

    # British motorsport flavor
    "Hamilton", "Russell", "Norris", "Button", "Hunt", "Mansell",
    "Coulthard", "Herbert", "Davidson", "Moss", "Hill", "Clark", "Brabham", "Collins", "Hawthorn", "Stewart",

    # ======================================================================
    # ITALIAN (125 names)
    # ======================================================================
    "Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo",
    "Ricci", "Marino", "Greco", "Bruno", "Gallo", "Conti", "De Luca", "Costa",
    "Giordano", "Mancini", "Rizzo", "Lombardi", "Moretti", "Barbieri", "Fontana",
    "Santoro", "Mariani", "Rinaldi", "Caruso", "Ferrara", "Vitale", "Leone",
    "Longo", "Antonelli", "Giovinazzi", "Fisichella", "Alboreto", "Zanardi",
    "Trulli", "Alesi", "Larini", "Bruni", "Nannini",
    
    # Additional Italian surnames
    "Bellini", "Cecchi", "D'Angelo", "Fabbri", "Gatti", "Grassi", "Ferri", "Monti", "Pellegrini", "Serra",
    "Testa", "Villa", "Bernardi", "Carbone", "Caputo", "Cattaneo", "Ferrero", "Gentile", "Orlando", "Parisi",
    "Rossetti", "Sala", "Sanna", "Silvestri", "Sorrentino", "De Angelis", "Bianco", "Marchetti", "Martino", "Palumbo",
    "Piras", "Sartori", "Benedetti", "De Santis", "Farina", "Galli", "Lombardo", "Martinelli", "Messina", "Negri",
    "Pagano", "Rizzi", "Ruggiero", "Simone", "Ferraro", "Basile", "Coppola", "D'Amico", "Giuliani", "Guerra",
    "Longo", "Mazza", "Milani", "Monaco", "Neri", "Poli", "Riva", "Rosso", "Valenti", "Baldini",
    "Barone", "Borghini", "Carboni", "Cavalli", "Chiesa", "Colombini", "Donati", "Fabbri", "Fiore", "Gennaro",
    "Innocenti", "Lanza", "Lucchesi", "Magnani", "Moro", "Nardi", "Pellegrino", "Pinto", "Pozzi", "Rizzo",
    "Rocca", "Salvatore", "Scarpa", "Stella", "Todaro",

    # ======================================================================
    # SPANISH / LATIN AMERICAN (115 names)
    # ======================================================================
    "Garcia", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Perez",
    "Sanchez", "Ramirez", "Torres", "Flores", "Rivera", "Gomez", "Diaz", "Cruz",
    "Morales", "Reyes", "Gutierrez", "Ortiz", "Chavez", "Ruiz", "Jimenez",
    "Moreno", "Alvarez", "Romero", "Mendoza", "Vargas", "Castillo", "Guzman",
    "Vazquez", "Alonso", "Sainz", "De la Rosa", "Montoya", "Guerrero",
    
    # Additional Spanish/Latin American surnames
    "Aguilar", "Blanco", "Castro", "Delgado", "Dominguez", "Espinosa", "Fernandez", "Fuentes", "Gallego", "Herrera",
    "Iglesias", "Juarez", "Leon", "Marquez", "Medina", "Molina", "Montiel", "Munoz", "Navarro", "Nunez",
    "Ortega", "Pena", "Ramos", "Rivas", "Rojas", "Rubio", "Salazar", "Santos", "Soto", "Suarez",
    "Torres", "Valdez", "Valencia", "Vega", "Velasquez", "Vera", "Villanueva", "Calderon", "Campos", "Carrillo",
    "Cervantes", "Cordova", "Cortez", "Crespo", "Duarte", "Escobar", "Figueroa", "Galvan", "Garza", "Gil",
    "Guerrero", "Guzman", "Herrera", "Ibanez", "Lara", "Lorenzo", "Luna", "Maldonado", "Marin", "Mayorga",
    "Mejia", "Miranda", "Montes", "Mora", "Murillo", "Nieto", "Ochoa", "Orozco", "Pacheco", "Palacios",
    "Paredes", "Pardo", "Pascual", "Paz", "Prieto", "Quintero", "Rios", "Salas", "Silva", "Solis",
    "Soriano", "Tamayo", "Toledo", "Uribe", "Varela", "Velasco", "Vicente", "Villarreal", "Zamora", "Zavala",

    # ======================================================================
    # GERMAN / AUSTRIAN / SWISS (125 names)
    # ======================================================================
    "Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Schroeder", "Koch", "Bauer", "Richter",
    "Klein", "Wolf", "Neumann", "Schwarz", "Zimmermann", "Braun", "Kruger",
    "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Krause", "Meier",
    "Lehmann",

    # German motorsport flavor
    "Schumacher", "Vettel", "Rosberg", "Ratzenberger", "Wendlinger",
    "Glock", "Hulkenberg", "Winkelhock", "Heidfeld", "Surer",
    
    # Additional German/Austrian/Swiss surnames
    "Bauer", "Bergmann", "Brandt", "Engel", "Friedrich", "Fuchs", "Graf", "Gross", "Hahn", "Heinrich",
    "Hermann", "Herzog", "Huber", "Jung", "Kaiser", "Keller", "Konig", "Kraus", "Lang", "Ludwig",
    "Maier", "Mayer", "Moser", "Otto", "Paul", "Peters", "Pfeiffer", "Roth", "Sauer", "Schafer",
    "Schenk", "Scherer", "Schiller", "Schreiber", "Schubert", "Seifert", "Sommer", "Stein", "Steiner", "Stock",
    "Sturm", "Vogel", "Vogt", "Volker", "Walter", "Weiss", "Wiegand", "Winter", "Wirth", "Wolff",
    "Ziegler", "Albrecht", "Arnold", "Bach", "Beer", "Berg", "Berger", "Berndt", "Bohm", "Busch",
    "Dietrich", "Dittrich", "Eckert", "Eichler", "Falk", "Fink", "Franz", "Frey", "Geiger", "Gerber",
    "Gottschalk", "Grimm", "Haas", "Hamm", "Hansen", "Haupt", "Heller", "Herold", "Herrmann", "Hildebrandt",
    "Hoppe", "Horn", "Jacobi", "Jaeger", "Janssen", "Kaufmann", "Kiefer", "Kirsch", "Klose", "Kolb",
    "Kraft", "Kress", "Kuhn", "Kunz", "Langer", "Lindner", "Lorenz", "Marx", "Mertens", "Michel",
    "Moller", "Moritz", "Nagel", "Naumann", "Nickel", "Novak", "Pohl", "Preis", "Prinz", "Rademacher",

    # ======================================================================
    # FRENCH / FRANCOPHONE (120 names)
    # ======================================================================
    "Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit",
    "Durand", "Leroy", "Moreau", "Simon", "Laurent", "Lefebvre", "Michel",
    "David", "Bertrand", "Roux", "Vincent", "Fournier", "Morel", "Girard",
    "Andre", "Lefevre", "Mercier", "Dupont", "Lambert", "Bonnet",
    "Francois", "Prost", "Arnoux", "Pironi", "Depailler", "Jabouille",
    "Laffite", "Beltoise", "Cevert", "Gasly", "Ocon",
    
    # Additional French surnames
    "Blanc", "Garnier", "Chevalier", "Rousseau", "Faure", "Renard", "Colin", "Vidal", "Caron", "Picard",
    "Roger", "Gauthier", "Gaillard", "Lemaire", "Renaud", "Roy", "Clement", "Leclerc", "Aubry", "Philippe",
    "Bourgeois", "Benoit", "Marchand", "Guillot", "Boyer", "Duval", "Besson", "Chevalier", "Perrier", "Dumas",
    "Brun", "Barbier", "Blanchard", "Briand", "Carre", "Gautier", "Guillaume", "Henry", "Hubert", "Jacquet",
    "Lopes", "Marty", "Masson", "Menard", "Meunier", "Nicolas", "Perrin", "Poirier", "Rey", "Royer",
    "Sanchez", "Schmitt", "Valentin", "Arnaud", "Baron", "Benard", "Berger", "Boucher", "Boyer", "Charles",
    "Collet", "Courtois", "Denis", "Deschamps", "Fernandez", "Fontaine", "Gay", "Gerard", "Giraud", "Humbert",
    "Jean", "Lacroix", "Leroux", "Maillard", "Mallet", "Martel", "Marechal", "Marie", "Meyer", "Olivier",
    "Pons", "Raymond", "Riviere", "Robin", "Rodriguez", "Santos", "Silva", "Tessier", "Weiss", "Bouchet",
    "Breton", "Carpentier", "Charpentier", "Cordier", "Delorme", "Fleury", "Guerin", "Huet", "Julien", "Poulain",

    # ======================================================================
    # SCANDINAVIAN (95 names)
    # ======================================================================
    "Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson",
    "Olsson", "Persson", "Svensson", "Gustafsson", "Pettersson", "Jonsson",
    "Jansson", "Hansson", "Bengtsson", "Jorgensen", "Madsen", "Kristensen",
    "Hansen", "Sorensen",

    # Nordic motorsport
    "Raikkonen", "Bottas", "Rosenqvist", "Ericsson", "Magnussen",
    "Lundgaard", "Blomqvist", "Salonen", "Kovalainen", "Valtonen",
    
    # Additional Scandinavian surnames
    "Berg", "Lindberg", "Lindgren", "Lund", "Bergstrom", "Engstrom", "Hedlund", "Holmberg", "Jakobsson", "Lindqvist",
    "Lundberg", "Magnusson", "Martinsson", "Mattsson", "Nielsen", "Nyberg", "Nyman", "Ohlsson", "Olin", "Oskarsson",
    "Paulsson", "Pedersen", "Sjoberg", "Strom", "Sundberg", "Wallin", "Westerberg", "Aberg", "Ahonen", "Andersen",
    "Axelsson", "Berggren", "Bergman", "Bjork", "Carlsson", "Danielsson", "Edlund", "Eliasson", "Forsberg", "Fransson",
    "Fredriksson", "Gren", "Gronberg", "Hakansson", "Hallberg", "Hjalmarsson", "Holmgren", "Isaksson", "Jensen", "Johnsson",
    "Juhani", "Korhonen", "Lahtinen", "Lehtonen", "Lindholm", "Lundgren", "Lundqvist", "Makinen", "Mikkelsen", "Nieminen",
    "Nordstrom", "Noren", "Olofsson", "Palmquist", "Rantanen", "Saarinen", "Sandberg", "Soder", "Svenningsson", "Virtanen",

    # ======================================================================
    # DUTCH / BELGIAN (95 names)
    # ======================================================================
    "De Jong", "Jansen", "De Vries", "Van den Berg", "Van Dijk", "Bakker",
    "Janssen", "Visser", "Smit", "Meijer", "De Boer", "Mulder", "De Groot",
    "Bos", "Vos", "Peters", "Hendriks", "Van Leeuwen", "Dekker", "Brouwer",

    # Benelux motorsport
    "Verstappen", "Vandoorne", "Van der Garde", "Albers",
    "Coronel", "Doornbos", "Bleekemolen", "Ickx", "Boutsen",
    
    # Additional Dutch/Belgian surnames
    "Van der Linden", "Willems", "Maes", "Jacobs", "Claes", "Goossens", "Wouters", "De Smet", "Vermeulen", "Peeters",
    "Van de Velde", "Claessens", "Hermans", "Aerts", "Pauwels", "Smits", "De Wilde", "Van Damme", "Martens", "Cools",
    "Bogaerts", "Stassen", "Michiels", "Hendrickx", "Claeys", "Engels", "Dubois", "Lambert", "Van den Eynde", "Simon",
    "De Cock", "Geerts", "Van Acker", "Diels", "Lemmens", "Van Hoof", "Nijs", "Coppens", "Sels", "Mertens",
    "Verhoeven", "Koster", "Van Loo", "Bergmans", "De Backer", "Schouten", "De Graaf", "Kuipers", "Van den Heuvel", "Hoekstra",
    "Kruger", "Van Beek", "Vermeer", "De Wit", "Scholten", "Van Dam", "Driessen", "Bosch", "Sanders", "Post",
    "Hendriks", "Huisman", "Van Es", "Van Rijn", "Brinkman", "Evers", "Dirksen", "Gerritsen", "Kuiper", "De Haas",
    "Klaassen", "Molenaar", "Roos", "Van den Broek", "Kok", "Schipper", "Vink", "Vries", "Steenbergen", "Van Dalen",

    # ======================================================================
    # EASTERN EUROPEAN / SLAVIC (85 names)
    # ======================================================================
    "Novak", "Horvat", "Kovac", "Krajnc", "Zupancic", "Vidmar", "Kovacic",
    "Marko", "Kuznetsov", "Petrov", "Ivanov", "Smirnov", "Popov", "Sokolov",
    "Lebedev", "Kozlov", "Novikov", "Morozov", "Volkov", "Andreev",
    "Mazepin", "Kvyat", "Sirotkin", "Aleshin", "Kubica",
    
    # Additional Eastern European/Slavic surnames
    "Kowalski", "Nowak", "Wisniewski", "Wojcik", "Lewandowski", "Kaminski", "Kowalczyk", "Zielinski", "Szymanski", "Mazur",
    "Pawlowski", "Krawczyk", "Piotrowski", "Grabowski", "Nowakowski", "Pawlak", "Michalski", "Zajac", "Krol", "Wieczorek",
    "Dudek", "Wrobel", "Jaworski", "Mazurek", "Adamczyk", "Ostrowski", "Duda", "Witkowski", "Sadowski", "Tomaszewski",
    "Vasilyev", "Mikhailov", "Alexandrov", "Nikolaev", "Stepanov", "Romanov", "Orlov", "Pavlov", "Kirov", "Fedorov",
    "Bogdanov", "Sergeyev", "Grigoriev", "Karpov", "Zakharov", "Belov", "Voronov", "Makarov", "Tarasov", "Frolov",
    "Antonov", "Filippov", "Egorov", "Medvedev", "Chernyshev", "Baranov", "Lazarev", "Vinogradov", "Golubev", "Kotov",

    # ======================================================================
    # JAPANESE (85 names)
    # ======================================================================
    "Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto",
    "Nakamura", "Kobayashi", "Kato", "Yoshida", "Yamada", "Sasaki",
    "Yamaguchi", "Saito", "Matsumoto", "Inoue", "Kimura", "Hayashi",
    "Shimizu", "Tsunoda", "Nakajima", "Matsushita", "Fukuzumi",
    "Makino", "Hirakawa",
    
    # Additional Japanese surnames
    "Fujita", "Ogawa", "Hasegawa", "Mori", "Ishikawa", "Maeda", "Kondo", "Sakamoto", "Aoki", "Okada",
    "Endo", "Fujii", "Goto", "Ikeda", "Ishii", "Kaneko", "Kawamura", "Kikuchi", "Kojima", "Kudo",
    "Matsui", "Miura", "Miyamoto", "Murakami", "Nakano", "Nishimura", "Oka", "Okamoto", "Ono", "Sakai",
    "Sakurai", "Shibata", "Sugimoto", "Takagi", "Takeuchi", "Tamura", "Taniguchi", "Tsuchiya", "Ueda", "Uchida",
    "Wada", "Yagi", "Yamazaki", "Yokoyama", "Yoshikawa", "Fukuda", "Harada", "Hiraoka", "Honda", "Hoshino",
    "Imai", "Ishida", "Iwasaki", "Kawakami", "Kitamura", "Kosaka", "Maruyama", "Matsuda", "Morita", "Nagai",

    # ======================================================================
    # CHINESE (70 names)
    # ======================================================================
    "Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu",
    "Zhou", "Xu", "Sun", "Ma", "Zhu", "Hu", "Guo", "He", "Gao", "Lin", "Luo",
    
    # Additional Chinese surnames
    "Zheng", "Liang", "Song", "Tang", "Xu", "Han", "Feng", "Deng", "Cao", "Peng",
    "Zeng", "Xiao", "Tian", "Dong", "Pan", "Yuan", "Cai", "Jiang", "Yu", "Du",
    "Ye", "Cheng", "Wei", "Ren", "Qiu", "Xie", "Zou", "Shi", "Liang", "Jin",
    "Long", "Tan", "Dai", "Qin", "Wan", "Xiong", "Lu", "Hao", "Kong", "Bai",
    "Cui", "Kang", "Mao", "Gu", "Lai", "Gong", "Shao", "Wan", "Qian", "Yan",

    # ======================================================================
    # BRAZILIAN / PORTUGUESE (85 names)
    # ======================================================================
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves",
    "Pereira", "Lima", "Gomes", "Ribeiro", "Martins", "Carvalho", "Rocha",
    "Almeida", "Nascimento", "Araujo", "Melo", "Barbosa",

    # Brazilian motorsport
    "Senna", "Fittipaldi", "Piquet", "Barrichello", "Massa", "Nasr",
    
    # Additional Brazilian/Portuguese surnames
    "Costa", "Teixeira", "Moreira", "Cunha", "Cardoso", "Monteiro", "Nunes", "Pinto", "Soares", "Dias",
    "Campos", "Correia", "Freitas", "Fernandes", "Mendes", "Marques", "Castro", "Lopes", "Moura", "Pires",
    "Ramos", "Reis", "Coelho", "Duarte", "Fonseca", "Machado", "Rosa", "Torres", "Viana", "Assis",
    "Batista", "Borges", "Braga", "Cavalcanti", "Cruz", "Farias", "Figueiredo", "Franco", "Guimaraes", "Lacerda",
    "Leal", "Macedo", "Medeiros", "Miranda", "Moraes", "Neves", "Pacheco", "Paiva", "Porto", "Resende",
    "Sa", "Santana", "Santiago", "Tavares", "Toledo", "Vargas", "Vaz", "Vieira", "Xavier", "Azevedo",

    # ======================================================================
    # AMERICAN / CANADIAN / AUSTRALIAN / NZ (150 names)
    # ======================================================================
    "Power", "Newgarden", "Pagenaud", "Dixon", "Rossi", "Herta", "O'Ward",
    "McLaughlin", "Palou", "Hunter-Reay", "Rahal", "Carpenter", "Hinchcliffe",
    "Wickens", "Andretti", "Foyt", "Unser", "Mears", "Franchitti",
    "Stroll", "Villeneuve", "Tracy", "Tagliani", "Carpentier",

    # Oceania
    "Ricciardo", "Webber", "Jones", "Brabham", "Piastri",
    "Van Gisbergen", "Whincup",
    
    # Additional American/Canadian surnames
    "Anderson", "Bailey", "Barnes", "Bennett", "Brooks", "Bryant", "Butler", "Campbell", "Carter", "Collins",
    "Cook", "Cooper", "Cox", "Cruz", "Diaz", "Edwards", "Ellis", "Evans", "Fisher", "Flores",
    "Foster", "Garcia", "Gomez", "Gonzalez", "Gray", "Green", "Griffin", "Hall", "Harris", "Hayes",
    "Henderson", "Hernandez", "Hill", "Howard", "Hughes", "Jackson", "James", "Jenkins", "Johnson", "Jordan",
    "Kelly", "King", "Lee", "Lewis", "Long", "Lopez", "Martin", "Martinez", "Miller", "Mitchell",
    "Moore", "Morgan", "Morris", "Murphy", "Myers", "Nelson", "Parker", "Patterson", "Perez", "Perry",
    "Peterson", "Phillips", "Powell", "Price", "Ramirez", "Reed", "Reynolds", "Richardson", "Rivera", "Roberts",
    "Robinson", "Rodriguez", "Rogers", "Ross", "Russell", "Sanchez", "Sanders", "Scott", "Simmons", "Smith",
    "Stewart", "Sullivan", "Taylor", "Thomas", "Thompson", "Torres", "Turner", "Walker", "Ward", "Washington",
    "Watson", "White", "Williams", "Wilson", "Wood", "Wright", "Young", "Allen", "Bell", "Bennett",
    
    # Additional Oceania surnames
    "Brown", "Clarke", "Davis", "Evans", "Fraser", "Gibson", "Graham", "Harris", "Hughes", "Johnston",
    "Kelly", "Kennedy", "King", "Lee", "Lewis", "Martin", "McDonald", "Mitchell", "Murphy", "Murray",
    "O'Brien", "Parker", "Reid", "Robertson", "Robinson", "Ross", "Ryan", "Scott", "Smith", "Taylor",
    "Thomas", "Thompson", "Walker", "Walsh", "Watson", "Williams", "Wilson", "Wright", "Young", "Anderson",

    # ======================================================================
    # MODERN FEEDER / GLOBAL (70 names)
    # ======================================================================
    "Armstrong", "Aitken", "Daruvala", "Lawson", "Hauger", "Vips", "Doohan",
    "Hadjar", "Bearman", "Crawford", "Bortoleto", "Verschoor", "Vesti",
    "Leclerc", "Pourchaire", "Drugovich", "Iwasa", "Maini",
    
    # Additional modern feeder surnames
    "Aron", "Beckmann", "Boschung", "Caldwell", "Chadwick", "Correa", "Darras", "Deletraz", "Deledda", "Fittipaldi",
    "Ghiotto", "Herta", "Hughes", "Ilott", "Lundgaard", "Mazepin", "Novalak", "O'Ward", "Piastri", "Piquet",
    "Prema", "Sargeant", "Schumacher", "Shwartzman", "Smolyar", "Stanek", "Ticktum", "Tsunoda", "Valtonen", "Zhou",
    "Artem", "Aron", "Boschung", "Canapino", "Collet", "Cordeel", "Doohan", "Edgar", "Famin", "Foster",
    "Frederick", "Ghiotto", "Goddard", "Hughes", "Iwasa", "Jensen", "Kikuchi", "Leclerc", "Lundqvist", "Malukas",
    "Nannini", "O'Sullivan", "Pasma", "Quinn", "Rasmussen", "Seguin", "Toth", "Ugran", "Vidales", "Weug",
    
    # ======================================================================
    # KOREAN (50 names)
    # ======================================================================
    "Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim",
    "Han", "Oh", "Seo", "Shin", "Kwon", "Song", "Hong", "Ahn", "Moon", "Yang",
    "Baek", "Ryu", "Nam", "Bae", "Ko", "Hwang", "Yoo", "Huh", "Noh", "Shim",
    "Ha", "Joo", "Koo", "Min", "Byun", "Bang", "Chung", "Sa", "Tae", "Sun",
    "Pyo", "Yeon", "Won", "Hwang", "Myung", "Doo", "Hwan", "Seok", "Kyung", "Chang",
    
    # ======================================================================
    # SOUTHEAST ASIAN (50 names)
    # ======================================================================
    "Nguyen", "Tran", "Le", "Pham", "Hoang", "Vo", "Dang", "Bui", "Do", "Ngo",
    "Duong", "Ly", "Ho", "Truong", "Phan", "Vu", "Doan", "Dinh", "Luong", "Trinh",
    "Abdullah", "Ahmad", "Ismail", "Mohamed", "Hassan", "Ibrahim", "Ali", "Rahman", "Omar", "Yusof",
    "Sulaiman", "Hashim", "Hussein", "Hamid", "Salleh", "Abdullah", "Karim", "Razak", "Jamal", "Amin",
    "Santos", "Cruz", "Reyes", "Ramos", "Garcia", "Gonzalez", "Fernandez", "Torres", "Mendoza", "Lopez"
]


# ============================================================================
# TEAM NAMES (600+ combinations)
# ============================================================================
TEAM_PREFIXES_GRASSROOTS = [
    "Local", "Valley", "County", "Regional", "Community", "Metro", "City", "Town", "District", "Provincial",
    "Riverside", "Hillside", "Lakeside", "Bayside", "Parkside", "Woodland", "Highland", "Coastal", "Mountain", "Prairie",
    # Additional grassroots prefixes
    "Suburban", "Township", "Campus", "Junction", "Crossroads", "Midtown", "Uptown", "Downtown", "Gateway", "Harbor",
    "Dockside", "Industrial", "Heritage", "Legacy", "Academy", "Institute", "Foundation", "Coalition", "Alliance", "Union",
    "Campus", "Village", "Borough", "Civic", "United", "Central", "Northern", "Southern", "Eastern", "Western",
    "Neighborhood", "Local", "Area", "Zone", "Quarter", "Section", "Division", "Settlement", "Colony", "Territory"
]

TEAM_PREFIXES_MID_TIER = [
    "United", "Dynamic", "Velocity", "Momentum", "Thunder", "Lightning", "Phoenix", "Eagle", "Falcon", "Hawk",
    "Titan", "Atlas", "Apex", "Summit", "Peak", "Zenith", "Horizon", "Frontier", "Vanguard", "Pioneer",
    "Nova", "Orion", "Eclipse", "Fusion", "Nexus", "Matrix", "Vector", "Vertex", "Pulse", "Surge",
    # Additional mid-tier prefixes
    "Vortex", "Tempest", "Blaze", "Storm", "Streak", "Rapid", "Swift", "Turbo", "Nitro", "Power",
    "Quantum", "Stellar", "Cosmic", "Plasma", "Electro", "Hyper", "Ultra", "Mega", "Super", "Prime",
    "Alpha", "Beta", "Gamma", "Delta", "Omega", "Sigma", "Phantom", "Shadow", "Silver", "Golden",
    "Force", "Impact", "Thrust", "Drive", "Charge", "Spark", "Flash", "Bolt", "Arrow", "Rocket",
    "Comet", "Meteor", "Star", "Lunar", "Solar", "Galactic", "Nebula", "Astral", "Celestial", "Radiant",
    "Velocity", "Thunder", "Strike", "Blitz", "Rush", "Dash", "Sprint", "Turbo", "Boost", "Nitro"
]

TEAM_PREFIXES_TOP_TIER = [
    "Prestige", "Elite", "Premier", "Supreme", "Imperial", "Royal", "Crown", "Sovereign", "Majestic", "Regal",
    "Platinum", "Diamond", "Gold", "Silver", "Azure", "Crimson", "Obsidian", "Sterling", "Titanium", "Carbon",
    # Additional top-tier prefixes
    "Distinguished", "Exclusive", "Pinnacle", "Summit", "Apex", "Zenith", "Ultimate", "Prime", "Excellence", "Luxe",
    "Noble", "Grand", "Paramount", "Supreme", "Dynasty", "Legacy", "Heritage", "Iconic", "Legendary", "Mythic",
    "Epic", "Stellar", "Celestial", "Divine", "Sacred", "Eternal", "Infinite", "Absolute", "Perfect", "Flawless",
    "Superior", "Premier", "Leading", "Dominant", "Champion", "Victory", "Triumph", "Success", "Glory", "Honor"
]

TEAM_SUFFIXES = [
    "Racing", "Motorsport", "Racing Team", "Motorsports", "Grand Prix", "Competition", "Performance",
    "Racing Group", "Sport", "Speed", "Racing Club", "Team", "Racing Division", "Racers", "Formula",
    "Technologies", "Engineering", "Racing Systems", "Dynamics", "Racing Works", "Motorsport Group",
    # Additional team suffixes
    "Speed Team", "Competition Group", "Performance Division", "Motorsport Academy", "Racing Institute",
    "Speed Academy", "Track Team", "Circuit Squad", "Race Division", "GP Team", "Formula Squad",
    "Racing Federation", "Speed Union", "Track Alliance", "Circuit Coalition", "Racing Syndicate",
    "Performance Lab", "Speed Works", "Racing Hub", "Motor Club", "Auto Sport", "Racing League",
    "Velocity Team", "Speed Group", "Race Team", "Motor Racing", "Auto Racing", "Circuit Racing",
    "Track Racing", "GP Racing", "Formula Team", "Pro Racing", "Elite Racing", "Champion Racing",
    "Victory Racing", "Triumph Motorsport", "Glory Racing", "Honor Team", "Pride Racing", "Spirit Motorsport"
]

# Sponsor-style team names (more realistic modern F1 style)
SPONSOR_TEAM_NAMES = [
    "Apex Computing Racing", "Velocity Networks GP", "Summit Capital Motorsport", "Horizon Investments Racing",
    "Titan Energy Formula", "Pulse Beverages Racing", "Nexus Technologies GP", "Vector Systems Racing",
    "Fusion Industries Motorsport", "Eclipse Financial Racing", "Nova Pharmaceuticals GP", "Orion Tech Racing",
    "Zenith Aerospace Formula", "Atlas Logistics Motorsport", "Phoenix Digital Racing", "Quantum Computing GP",
    "Helix Biotech Racing", "Prism Media Motorsport", "Spectrum Communications GP", "Vortex Energy Racing",
    # Additional sponsor team names
    "Quantum Energy GP", "Helix Pharma Racing", "Prism Digital Motorsport", "Cipher Security Racing",
    "Vertex Cloud GP", "Synergy Tech Racing", "Infinity Finance Formula", "Matrix Media Motorsport",
    "Vortex Power Racing", "Tempest Energy GP", "Blaze Technologies Racing", "Storm Analytics GP",
    "Streak Systems Motorsport", "Rapid Cloud Racing", "Swift Networks GP", "Lightning Data Racing",
    "Thunder Computing Formula", "Spark Solutions GP", "Flash Energy Racing", "Bolt Systems Motorsport",
    "Arrow Technologies GP", "Rocket Power Racing", "Comet Digital Formula", "Meteor Analytics GP",
    "Star Networks Racing", "Lunar Systems Motorsport", "Solar Energy GP", "Galactic Tech Racing",
    "Nebula Computing Formula", "Astral Solutions GP", "Celestial Power Racing", "Radiant Energy Motorsport",
    "Velocity Data GP", "Impact Systems Racing", "Thrust Technologies Formula", "Drive Solutions GP",
    "Charge Energy Racing", "Platinum Financial GP", "Diamond Asset Racing", "Crown Capital Motorsport"
]

# ============================================================================
# SPONSOR BRANDS (300+)
# ============================================================================
SPONSOR_BRANDS_TECH = [
    "Apex Computing", "Velocity Networks", "Nexus Technologies", "Vector Systems", "Fusion Cloud",
    "Eclipse Software", "Nova Digital", "Orion Tech", "Zenith Data", "Quantum Computing",
    "Helix Biotech", "Prism Media", "Spectrum Communications", "Vortex Solutions", "Matrix Analytics",
    "Cipher Security", "Vertex AI", "Pulse Innovations", "Synergy Systems", "Infinity Tech",
    # Additional tech brands
    "Byte Systems", "Cloud Nine Tech", "Data Stream", "Neural Networks", "Quantum Leap",
    "Silicon Edge", "Cyber Solutions", "Digital Forge", "Tech Horizon", "Binary Labs",
    "Code Velocity", "Net Dynamics", "Web Innovations", "App Masters", "Software Prime",
    "Logic Systems", "Core Tech", "Pixel Perfect", "Nano Solutions", "Micro Dynamics",
    "Mega Computing", "Giga Networks", "Tera Data", "Ultra Systems", "Hyper Tech",
    "Smart Solutions", "Bright Ideas Tech", "Future Systems", "Next Gen Computing", "Advanced Tech",
    "Pioneer Digital", "Frontier Systems", "Horizon Computing", "Vista Technology", "Summit Solutions",
    "Peak Performance Tech", "Apex Analytics", "Prime Computing", "Alpha Systems", "Beta Networks",
    "Gamma Solutions", "Delta Tech", "Omega Computing", "Sigma Systems", "Theta Networks",
    "Lambda Solutions", "Kappa Tech", "Iota Computing", "Zeta Systems", "Eta Networks",
    "Epsilon Solutions", "Proto Tech", "Meta Systems", "Para Computing", "Omni Networks"
]

SPONSOR_BRANDS_FINANCE = [
    "Summit Capital", "Horizon Investments", "Eclipse Financial", "Atlas Bank", "Titan Holdings",
    "Zenith Asset Management", "Phoenix Capital", "Apex Ventures", "Vertex Wealth", "Nexus Finance",
    "Prestige Private Banking", "Premier Trust", "Imperial Securities", "Crown Capital", "Sterling Investments",
    "Diamond Asset Group", "Platinum Financial", "Gold Standard Bank", "Azure Capital", "Crimson Investments",
    # Additional finance brands
    "Trinity Bank", "Fortune Capital", "Wealth Advisors", "Prime Trust", "Capital One Investments",
    "Global Assets", "Portfolio Masters", "Prime Securities", "Elite Banking", "Fortune Group",
    "Prosperity Capital", "Legacy Wealth", "Dynasty Finance", "Empire Trust", "Crown Banking",
    "Royal Investments", "Noble Capital", "Grand Financial", "Supreme Bank", "Premier Securities",
    "Excellence Capital", "Victory Investments", "Triumph Financial", "Success Bank", "Glory Capital",
    "Honor Financial", "Pride Investments", "Spirit Bank", "Valor Capital", "Merit Financial",
    "Trust Financial", "Secure Investments", "Safe Capital", "Solid Bank", "Stable Financial",
    "Growth Capital", "Progress Investments", "Advance Financial", "Forward Bank", "Future Capital",
    "Vision Investments", "Insight Financial", "Wisdom Bank", "Prudent Capital", "Sage Investments",
    "Strategic Financial", "Tactical Bank", "Smart Capital", "Savvy Investments", "Clever Financial",
    "Bold Bank", "Brave Capital", "Daring Investments", "Venture Financial", "Risk Bank"
]

SPONSOR_BRANDS_ENERGY = [
    "Titan Energy", "Pulse Power", "Vortex Energy", "Nova Renewables", "Eclipse Oil & Gas",
    "Zenith Energy", "Apex Petroleum", "Vector Energy Solutions", "Fusion Power", "Quantum Energy",
    "Thunder Energy", "Lightning Power", "Phoenix Energy", "Horizon Energy", "Summit Power",
    # Additional energy brands
    "Solar Dynamics", "Wind Power Solutions", "Green Energy Corp", "Sustainable Power", "Eco Energy",
    "Renewable Solutions", "Clean Power Inc", "Hydro Energy", "Geothermal Systems", "Bio Fuel Group",
    "Carbon Zero", "Green Grid", "Power Stream", "Energy Plus", "Volt Systems",
    "Electron Energy", "Photon Power", "Proton Energy", "Ion Solutions", "Plasma Power",
    "Nuclear Solutions", "Atomic Energy", "Thermal Power", "Heat Systems", "Steam Energy",
    "Flow Power", "Current Energy", "Circuit Solutions", "Charge Power", "Spark Energy",
    "Flash Power", "Bolt Energy", "Strike Solutions", "Shock Power", "Zap Energy"
]

SPONSOR_BRANDS_CONSUMER = [
    "Pulse Beverages", "Titan Sports Drinks", "Apex Nutrition", "Velocity Apparel", "Thunder Gear",
    "Lightning Shoes", "Phoenix Fashion", "Eagle Outfitters", "Falcon Sportswear", "Hawk Athletics",
    "Zenith Watches", "Summit Eyewear", "Horizon Travel", "Atlas Luggage", "Nexus Electronics",
    # Additional consumer brands
    "Fresh Drinks Co", "Snack Masters", "Energy Plus", "Sport Fuel", "Active Wear",
    "Speed Shoes", "Track Gear", "Racing Apparel", "Performance Wear", "Elite Fashion",
    "Sport Style", "Dynamic Threads", "Velocity Clothing", "Swift Footwear", "Rapid Fashion",
    "Quick Apparel", "Fast Track Wear", "Sprint Style", "Dash Clothing", "Rush Fashion",
    "Turbo Wear", "Nitro Style", "Boost Clothing", "Power Fashion", "Force Apparel",
    "Impact Wear", "Thrust Style", "Drive Clothing", "Charge Fashion", "Spark Apparel",
    "Flash Wear", "Bolt Style", "Arrow Clothing", "Rocket Fashion", "Comet Apparel"
]

SPONSOR_BRANDS_AUTOMOTIVE = [
    "Titan Tires", "Apex Performance Parts", "Velocity Lubricants", "Thunder Brakes", "Lightning Suspension",
    "Phoenix Engine Oil", "Eagle Transmissions", "Vector Composites", "Fusion Materials", "Quantum Adhesives",
    "Zenith Aerodynamics", "Summit Engineering", "Horizon Composites", "Atlas Bearings", "Nexus Electronics",
    # Additional automotive brands
    "Speed Parts Co", "Racing Components", "Performance Upgrades", "Turbo Systems", "Aero Dynamics",
    "Carbon Works", "Titanium Tech", "Racing Alloys", "Speed Bearings", "Performance Gaskets",
    "Elite Filters", "Racing Radiators", "Cool Systems", "Exhaust Masters", "Brake Specialists",
    "Clutch Pro", "Gearbox Experts", "Drivetrain Solutions", "Axle Tech", "Wheel Masters",
    "Suspension Pro", "Shock Absorbers Plus", "Spring Systems", "Damper Tech", "Coilover Specialists",
    "Fuel Injection Pro", "Ignition Systems", "Spark Tech", "Battery Masters", "Alternator Pro",
    "Starter Systems", "Electrical Solutions", "Wiring Pro", "Sensor Tech", "ECU Masters"
]

# ============================================================================
# NAME GENERATION FUNCTIONS
# ============================================================================

def _hash_to_index(seed: int, role: str, entity_id: int, pool_size: int) -> int:
    """Generate deterministic index from seed components"""
    combined = f"{seed}_{role}_{entity_id}"
    hash_val = int(hashlib.sha256(combined.encode()).hexdigest(), 16)
    return hash_val % pool_size


def generate_name(seed: int, role: str, entity_id: int, gender: Optional[str] = None) -> str:
    """
    Generate a deterministic human name for an entity.
    
    Args:
        seed: Simulation seed for determinism
        role: Entity role (Driver, Engineer, Mechanic, etc.)
        entity_id: Unique entity ID
        gender: Optional gender override. If None, determined probabilistically.
    
    Returns:
        "FirstName LastName"
    """
    # Determine gender if not provided
    if gender is None:
        # Use entity_id as additional entropy for gender determination
        gender_hash = _hash_to_index(seed, f"{role}_gender", entity_id, 100)
        
        if role == "Driver":
            # 15% female drivers
            is_female = gender_hash < 15
        elif role in ["Engineer", "Mechanic", "Strategist"]:
            # 25% female engineers/mechanics/strategists
            is_female = gender_hash < 25
        else:
            # 10% female principals (realistic for motorsport management)
            is_female = gender_hash < 10
        
        gender = "female" if is_female else "male"
    
    # Select first name pool
    if gender == "female":
        first_pool = FIRST_NAMES_FEMALE
    else:
        first_pool = FIRST_NAMES_MALE
    
    # Generate name indices
    first_idx = _hash_to_index(seed, f"{role}_first", entity_id, len(first_pool))
    last_idx = _hash_to_index(seed, f"{role}_last", entity_id, len(SURNAMES))
    
    first_name = first_pool[first_idx]
    last_name = SURNAMES[last_idx]
    
    return f"{first_name} {last_name}"


def generate_team_name(seed: int, tier: int, league_id: int, team_idx: int) -> str:
    """
    Generate a deterministic team name appropriate for the tier.
    
    Args:
        seed: Simulation seed
        tier: League tier (1=Grassroots, 5=Formula Z)
        league_id: League ID within tier
        team_idx: Team index within league
    
    Returns:
        Team name string
    """
    # Combine all inputs for unique hash
    combined_id = seed + (tier * 10000) + (league_id * 100) + team_idx
    
    # Formula Z (Tier 5) and Formula Y (Tier 4) use sponsor-style names
    if tier >= 4:
        name_idx = _hash_to_index(seed, f"team_tier{tier}", combined_id, len(SPONSOR_TEAM_NAMES))
        return SPONSOR_TEAM_NAMES[name_idx]
    
    # Select prefix pool based on tier
    if tier == 1:
        prefix_pool = TEAM_PREFIXES_GRASSROOTS
    elif tier in [2, 3]:
        prefix_pool = TEAM_PREFIXES_MID_TIER
    else:
        prefix_pool = TEAM_PREFIXES_TOP_TIER
    
    # Generate prefix and suffix
    prefix_idx = _hash_to_index(seed, f"team_prefix_t{tier}", combined_id, len(prefix_pool))
    suffix_idx = _hash_to_index(seed, f"team_suffix_t{tier}", combined_id, len(TEAM_SUFFIXES))
    
    prefix = prefix_pool[prefix_idx]
    suffix = TEAM_SUFFIXES[suffix_idx]
    
    return f"{prefix} {suffix}"


def generate_sponsor_name(seed: int, tier: int, sponsor_idx: int) -> str:
    """
    Generate a deterministic sponsor brand name.
    
    Args:
        seed: Simulation seed
        tier: Team tier (affects sponsor prestige)
        sponsor_idx: Index for uniqueness
    
    Returns:
        Sponsor brand name
    """
    # Higher tier teams get more prestigious sponsors
    if tier >= 4:
        # Top tier: Mix of all sponsor types
        all_sponsors = (SPONSOR_BRANDS_TECH + SPONSOR_BRANDS_FINANCE + 
                       SPONSOR_BRANDS_ENERGY + SPONSOR_BRANDS_AUTOMOTIVE)
    elif tier >= 3:
        # Mid tier: Tech, Energy, Consumer
        all_sponsors = SPONSOR_BRANDS_TECH + SPONSOR_BRANDS_ENERGY + SPONSOR_BRANDS_CONSUMER
    else:
        # Lower tier: Consumer and automotive
        all_sponsors = SPONSOR_BRANDS_CONSUMER + SPONSOR_BRANDS_AUTOMOTIVE
    
    idx = _hash_to_index(seed, f"sponsor_t{tier}", sponsor_idx, len(all_sponsors))
    return all_sponsors[idx]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_first_name(full_name: str) -> str:
    """Extract first name from full name"""
    return full_name.split()[0] if full_name else ""


def get_last_name(full_name: str) -> str:
    """Extract last name from full name"""
    parts = full_name.split()
    return parts[-1] if len(parts) > 1 else parts[0]


def get_initials(full_name: str) -> str:
    """Get initials from full name (e.g., 'Lewis Hamilton' -> 'LH')"""
    parts = full_name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[-1][0]}".upper()
    elif len(parts) == 1:
        return parts[0][0].upper()
    return "?"


# ============================================================================
# TRACK NAME GENERATION
# ============================================================================

# Track location descriptors
TRACK_LOCATIONS = [
    # ------------------------------------------------------------------
    # Geographic features
    # ------------------------------------------------------------------
    "Coastal", "Mountain", "Valley", "Desert", "Lakeside", "Riverside",
    "Highland", "Forest", "Island", "Peninsula", "Harbor", "Bay",
    "Ridge", "Summit",
    # Additional geographic features
    "Canyon", "Gorge", "Plateau", "Wetlands", "Marsh", "Swamp", "Delta", "Estuary", "Fjord", "Inlet",
    "Lagoon", "Mesa", "Plain", "Savanna", "Steppe", "Tundra", "Basin", "Bluff", "Butte", "Cliff",
    "Cove", "Creek", "Dune", "Falls", "Glacier", "Gully", "Heath", "Hill", "Knoll", "Lake",

    # ------------------------------------------------------------------
    # Regions / macro descriptors (generic, non-licensed)
    # ------------------------------------------------------------------
    "Northern", "Southern", "Eastern", "Western", "Central",
    "Atlantic", "Pacific", "Continental", "Capital",
    "Metropolitan", "Provincial", "Regional", "National",
    # Additional regional descriptors
    "Tri-State", "Northeast", "Southeast", "Midwest", "Southwest", "Northwest",
    "Gulf Coast", "Great Lakes", "Mountain States", "Sun Belt", "Rust Belt",
    "Interior", "Frontier", "Borderland", "Heartland", "Lowland", "Upland",

    # ------------------------------------------------------------------
    # Cultural / historical tone
    # ------------------------------------------------------------------
    "Heritage", "Historic", "Royal", "Imperial", "Grand",
    "International", "Mundial", "Crown", "Premier",
    "Elite", "Classic", "Legacy", "Iconic", "Legendary",

    # ------------------------------------------------------------------
    # REAL-WORLD CITY / METRO DESCRIPTORS (safe, non-licensed)
    # Use as adjectives, not official circuits
    # ------------------------------------------------------------------

    # North America  
    "Toronto", "Montreal", "Vancouver", "Calgary",
    "New York", "Chicago", "Detroit", "Austin",
    "Miami", "Los Angeles", "San Francisco",
    "Seattle", "Denver", "Phoenix", "Las Vegas",
    "Boston", "Philadelphia", "Atlanta", "Dallas",
    "Houston", "Minneapolis", "Portland", "Indianapolis",
    "Charlotte", "Nashville", "Memphis", "New Orleans",
    "San Diego", "San Jose", "Sacramento", "Salt Lake City",
    "Kansas City", "Milwaukee", "Cincinnati", "Cleveland",
    "Pittsburgh", "St. Louis", "Tampa", "Orlando",
    "Baltimore", "Washington", "Richmond", "Raleigh",

    # Europe
    "Frankfurt", "Munich", "Berlin", "Hamburg",
    "London", "Silverstone",  # tone-only, not venue
    "Paris", "Lyon", "Marseille",
    "Milan", "Monza",         # tone-only
    "Rome", "Barcelona", "Madrid",
    "Amsterdam", "Vienna", "Prague",
    "Budapest", "Warsaw",
    "Spa", "Ardennes",        # regional flavor
    "Stockholm", "Helsinki",
    "Birmingham", "Manchester", "Leeds", "Edinburgh", "Glasgow",
    "Brussels", "Antwerp", "Ghent", "Liege",
    "Copenhagen", "Oslo", "Gothenburg", "Bergen",
    "Lisbon", "Porto", "Valencia", "Seville",
    "Naples", "Turin", "Florence", "Bologna",
    "Cologne", "Stuttgart", "Dresden", "Leipzig",
    "Athens", "Thessaloniki", "Istanbul", "Ankara",
    "Dublin", "Cork", "Zurich", "Geneva",

    # Asia
    "Shanghai", "Beijing", "Shenzhen",
    "Hong Kong", "Macau",
    "Tokyo", "Osaka", "Nagoya",
    "Seoul", "Busan",
    "Singapore",
    "Bangkok", "Kuala Lumpur",
    "Jakarta", "Manila",
    "Taipei", "Kaohsiung", "Hanoi", "Ho Chi Minh",
    "Delhi", "Mumbai", "Bangalore", "Hyderabad",
    "Chennai", "Kolkata", "Pune", "Ahmedabad",
    "Karachi", "Lahore", "Islamabad", "Dhaka",

    # Middle East
    "Dubai", "Abu Dhabi", "Doha",
    "Riyadh", "Jeddah",
    "Kuwait City", "Manama", "Muscat", "Amman",
    "Beirut", "Damascus", "Baghdad", "Tehran",

    # South America
    "São Paulo", "Rio", "Interlagos",  # tone-only
    "Buenos Aires", "Cordoba",
    "Santiago", "Lima", "Bogotá",
    "Brasilia", "Salvador", "Fortaleza", "Recife",
    "Montevideo", "Asuncion", "La Paz", "Quito",
    "Caracas", "Medellin", "Cartagena", "Cali",

    # Oceania
    "Melbourne", "Sydney", "Adelaide",
    "Perth", "Auckland",
    "Brisbane", "Gold Coast", "Wellington", "Christchurch",
    "Canberra", "Newcastle", "Hobart", "Darwin",

    # Africa
    "Cape Town", "Johannesburg",
    "Durban", "Casablanca", "Marrakesh",
    "Cairo", "Alexandria", "Lagos", "Nairobi",
    "Accra", "Dakar", "Addis Ababa", "Tunis",
    "Algiers", "Lusaka", "Harare", "Maputo",
    
    # Fictional/Atmospheric locations
    "Silver Lake", "Red Rock", "Blue Mountain", "Green Valley", "Golden Gate",
    "Crystal Bay", "Emerald Coast", "Sapphire Ridge", "Ruby Falls", "Diamond Peak",
    "Thunder Valley", "Lightning Ridge", "Storm Harbor", "Tempest Bay", "Hurricane Point",
    "Sunset Strip", "Sunrise Valley", "Twilight Ridge", "Dawn Harbor", "Midnight Bay",
    "Eagle's Nest", "Falcon Ridge", "Hawk Valley", "Phoenix Point", "Raven Harbor",
    "Wolf Creek", "Bear Mountain", "Tiger Bay", "Lion's Gate", "Panther Ridge",
    "Star Valley", "Moon Harbor", "Sun Ridge", "Aurora Bay", "Eclipse Point",
    "Victory Lane", "Champion Ridge", "Triumph Valley", "Glory Bay", "Honor Point",
    "Speed Valley", "Velocity Ridge", "Rapid Harbor", "Swift Bay", "Quick Point"
]

# Track type descriptors
TRACK_TYPES = [
    "Circuit", "Raceway", "Speedway", "Park", "Ring", "Track", "Course",
    "Arena", "Complex", "Autodrome", "Motorplex", "Racing Ground", "Grand Prix Circuit",
    # Additional track types
    "Street Circuit", "Road Course", "Oval Track", "Superspeedway", "Short Track",
    "Karting Complex", "Test Track", "Proving Ground", "Race Course", "Motor Speedway",
    "Racing Venue", "Circuit Park", "Speed Circuit", "Racing Facility", "Motorsport Center",
    "Racing Ground", "Speed Track", "Competition Circuit", "Performance Track", "Racing Arena",
    "International Circuit", "National Speedway", "Championship Track", "Grand Prix Park", "Formula Circuit",
    "Racing Complex", "Motorsport Facility", "Speed Park"
]

# Track character descriptors (for lore)
TRACK_CHARACTERS = [
    "Known for its challenging chicanes and elevation changes",
    "Features long straights ideal for overtaking",
    "Tight and technical circuit demanding precision",
    "High-speed layout with sweeping corners",
    "Street-style circuit with minimal run-off",
    "Power circuit testing top speeds",
    "Mechanical grip showcase with low-speed corners",
    "Aero-dependent track with high downforce sections",
    "Historic venue with a rich racing legacy",
    "Modern facility with cutting-edge amenities",
    "Punishing on tyres with abrasive surfaces",
    "Rewarding smooth driving styles",
    "Features a dramatic final-corner overtaking spot",
    "Known for unpredictable weather conditions",
    "Fan-favorite venue with excellent viewing",
    # Additional track characters
    "Famous for dramatic last-lap battles",
    "Notorious for heavy brake wear",
    "Offers spectacular night racing under lights",
    "Challenges drivers with blind crests",
    "Features a unique figure-eight layout",
    "Combines high-speed and technical sections perfectly",
    "Known for its signature corner complex",
    "Tests both car and driver to the limit",
    "Favors aggressive driving styles",
    "Rewards patience and strategy",
    "Provides multiple racing lines",
    "Features minimal elevation changes",
    "Known for its bumpy surface character",
    "Offers natural amphitheater viewing",
    "Features state-of-the-art safety systems",
    "Notorious for unpredictable winds",
    "Famous for sunset racing conditions",
    "Known for its challenging final sector",
    "Features innovative track surface technology",
    "Rewards precise throttle control",
    "Known for its banking in key corners",
    "Features unique cross-over bridges",
    "Offers exceptional overtaking opportunities",
    "Tests fuel efficiency strategies",
    "Known for its dramatic podium location",
    "Features iconic grandstand architecture",
    "Rewards aerodynamic efficiency",
    "Known for its challenging pit lane entry",
    "Features multiple DRS zones"
]


def generate_track_name(seed: int, track_idx: int) -> Tuple[str, str]:
    """
    Generate a deterministic track name and character.
    
    Args:
        seed: Simulation seed
        track_idx: Track index for uniqueness
    
    Returns:
        Tuple of (track_name, track_character)
    """
    # Generate location and type
    location_idx = _hash_to_index(seed, "track_location", track_idx, len(TRACK_LOCATIONS))
    type_idx = _hash_to_index(seed, "track_type", track_idx, len(TRACK_TYPES))
    character_idx = _hash_to_index(seed, "track_character", track_idx, len(TRACK_CHARACTERS))
    
    location = TRACK_LOCATIONS[location_idx]
    track_type = TRACK_TYPES[type_idx]
    character = TRACK_CHARACTERS[character_idx]
    
    # Combine into name
    track_name = f"{location} {track_type}"
    
    return (track_name, character)


# ============================================================================
# LEAGUE NAME GENERATION
# ============================================================================

# League descriptors for procedural naming
LEAGUE_REGIONS = [
    "Northern", "Southern", "Eastern", "Western", "Central", "Atlantic", "Pacific",
    "Continental", "National", "International", "Regional", "Provincial", "Metropolitan",
    "Coastal", "Mountain", "Valley", "Riverside", "Lakeside", "Highland", "Prairie",
    "European", "American", "Asian", "Global", "World", "Premier", "Elite", "Grand",
    # Additional league regions
    "Tri-State", "Northeast", "Southeast", "Midwest", "Southwest", "Northwest",
    "Gulf Coast", "Great Lakes", "Sun Belt", "Rust Belt", "Interior",
    "Mediterranean", "Scandinavian", "Baltic", "Adriatic", "Caribbean", "South Pacific",
    "Intercontinental", "Transcontinental", "Pan-American", "Euro-Asian", "Indo-Pacific",
    "Arctic", "Tropical", "Equatorial", "Polar", "Temperate", "Subtropical",
    "Alpine", "Desert", "Forest", "Island", "Peninsula", "Archipelago",
    "Cross-Border", "Multi-State", "Interstate", "Interprovincial", "Cross-Region",
    "Heritage", "Historic", "Classic", "Modern", "Contemporary", "Traditional",
    "United", "Allied", "Federation", "Union", "League", "Association",
    "Summit", "Horizon", "Frontier", "Pioneer", "Vanguard", "Advanced"
]

LEAGUE_TYPES_GRASSROOTS = [
    "Sprint Series", "Circuit Championship", "Racing League", "Motorsport Club",
    "Racing Series", "Speed Championship", "Competition League", "Formula Series",
    "Touring Championship", "Driver's Cup", "Racing Trophy", "Challenge Series",
    # Additional grassroots types
    "Amateur Cup", "Regional Trophy", "County Championship", "District Series", "Local Cup",
    "Community Challenge", "Development League", "Junior Series", "Novice Championship",
    "Beginner Cup", "Entry Series", "Foundation League", "Starter Championship",
    "Rookie Cup", "Youth Series", "Cadet Championship", "Junior Cup", "Development Trophy",
    "Training Series", "Academy Championship", "Institute Cup", "School Series", "College Trophy",
    "University Championship", "Club Cup"
]

LEAGUE_TYPES_MID_TIER = [
    "Championship", "Grand Prix Series", "Formula League", "Racing Championship",
    "Motorsport Series", "Grand Challenge", "Premier League", "Elite Championship",
    "Professional Series", "Competition Cup", "Racing Federation", "Masters Series",
    # Additional mid-tier types
    "National Trophy", "Continental Cup", "Regional Grand Prix", "Professional Cup",
    "Advanced Series", "Expert Championship", "Competitive League", "Semi-Pro Series",
    "Development Cup", "Futures Championship", "Rising Stars Series", "Emerging Talent Cup",
    "Intermediate Championship", "Mid-Level Series", "Progressive Cup", "Advancing League",
    "Growing Championship", "Ascending Series", "Climbing Cup", "Upward League",
    "Forward Championship",  "Progress Series", "Evolution Cup", "Advancement League"
]

LEAGUE_TYPES_TOP_TIER = [
    "World Championship", "Grand Prix Championship", "International Series",
    "Global Championship", "Premier Championship", "Elite Grand Prix",
    "World Series", "International Federation", "Grand Challenge Cup",
    # Additional top-tier types
    "World Trophy", "Global Grand Prix", "Ultimate Championship", "Supreme Series",
    "Masters Cup", "Champions League", "Elite Trophy", "Prime Championship",
    "Prestige Series", "Pinnacle Cup", "Mundial Championship", "Apex Series",
    "Summit Cup", "Zenith Championship", "Crown Series", "Imperial Cup",
    "Royal Championship", "Grand Masters Series", "Legends Cup", "Icons Championship",
    "Heritage Series", "Classic Cup"
]


def generate_league_name(seed: int, tier: int, league_index: int) -> str:
    """
    Generate a deterministic league name appropriate for the tier.
    
    Args:
        seed: Simulation seed
        tier: League tier (1=Grassroots, 5=Formula Z)
        league_index: League index within tier
    
    Returns:
        League name string (e.g., "Northern Sprint Series", "Pacific Grand Prix Championship")
    """
    # Combine inputs for unique hash
    combined_id = seed + (tier * 1000) + league_index
    
    # Select region
    region_idx = _hash_to_index(seed, f"league_region_t{tier}", combined_id, len(LEAGUE_REGIONS))
    region = LEAGUE_REGIONS[region_idx]
    
    # Select type based on tier
    if tier == 1:
        type_pool = LEAGUE_TYPES_GRASSROOTS
    elif tier in [2, 3]:
        type_pool = LEAGUE_TYPES_MID_TIER
    else:
        type_pool = LEAGUE_TYPES_TOP_TIER
    
    type_idx = _hash_to_index(seed, f"league_type_t{tier}", combined_id, len(type_pool))
    league_type = type_pool[type_idx]
    
    # Combine into name
    league_name = f"{region} {league_type}"
    
    return league_name


# ============================================================================
# MANUFACTURER & PART NAME GENERATION (Phase 1)
# ============================================================================

def generate_manufacturer_name(seed: int, manufacturer_id: int, heritage_template) -> str:
    """
    Generate a deterministic manufacturer name based on heritage template.
    
    Args:
        seed: Simulation seed
        manufacturer_id: Unique manufacturer ID
        heritage_template: HeritageTemplate with naming_grammar
    
    Returns:
        Manufacturer name (e.g., "TakaGawa Dynamics", "Kraft Motor", "Rossi Racing")
    """
    import hashlib
    from typing import List
    
    # Create deterministic RNG for this manufacturer
    input_str = f"{seed}:manufacturer:{manufacturer_id}"
    hash_int = int(hashlib.md5(input_str.encode()).hexdigest(), 16)
    
    # Use hash to select from naming grammar
    grammar = heritage_template.naming_grammar
    pattern = grammar.get("patterns", ["compound"])[hash_int % len(grammar.get("patterns", ["compound"]))]
    
    prefixes = grammar.get("prefixes", ["Racing"])
    suffixes = grammar.get("suffixes", ["Motorsport"])
    
    prefix_idx = hash_int % len(prefixes)
    suffix_idx = (hash_int // len(prefixes)) % len(suffixes)
    
    prefix = prefixes[prefix_idx]
    suffix = suffixes[suffix_idx]
    
    # Apply pattern
    if pattern == "compound":
        return f"{prefix}{suffix}"
    elif pattern == "suffix":
        return f"{prefix}{suffix}"
    elif pattern == "formal":
        return f"{prefix} {suffix}"
    elif pattern == "surname":
        return f"{prefix} {suffix}"
    elif pattern == "passionate":
        return f"{prefix} {suffix}"
    elif pattern == "bold":
        return f"{prefix} {suffix}"
    elif pattern == "nordic":
        return f"{prefix}{suffix}"
    elif pattern == "elegant":
        return f"{prefix} {suffix}"
    elif pattern == "modern" or pattern == "tech":
        return f"{prefix} {suffix}"
    else:
        return f"{prefix} {suffix}"


def generate_part_model_name(seed: int, part_id: str, manufacturer_name: str, part_type: str, generation: int) -> str:
    """
    Generate a deterministic part model name.
    
    Args:
        seed: Simulation seed
        part_id: Unique part ID
        manufacturer_name: Name of manufacturer
        part_type: Type of part (engine, chassis, aero_package, etc.)
        generation: Part generation number (1, 2, 3, etc.)
    
    Returns:
        Part model name (e.g., "TakaGawa Engine Mk3", "Vector Aero Package Evo")
    """
    import hashlib
    
    # Generation suffix patterns
    generation_suffixes = [
        f"Mk{generation}",
        f"Gen{generation}",
        "Evo" if generation > 1 else "Base",
        "R" if generation > 1 else "S",
        "Z" if generation > 2 else "X" if generation > 1 else "V",
        f"Ultra" if generation > 3 else "Pro" if generation > 2 else "Plus" if generation > 1 else ""
    ]
    
    # Create deterministic selection
    input_str = f"{seed}:part:{part_id}"
    hash_int = int(hashlib.md5(input_str.encode()).hexdigest(), 16)
    
    suffix = generation_suffixes[hash_int % len(generation_suffixes)]
    
    # Format part type for display
    part_type_display = part_type.replace("_", " ").title()
    
    # Combine
    if suffix:
        return f"{manufacturer_name} {part_type_display} {suffix}"
    else:
        return f"{manufacturer_name} {part_type_display}"
