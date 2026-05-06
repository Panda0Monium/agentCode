FROM agentcode-base
RUN pip install --no-cache-dir pillow openpyxl nltk python-docx PyPDF2
RUN python -c "\
import nltk; \
nltk.download('averaged_perceptron_tagger'); \
nltk.download('punkt'); \
nltk.download('wordnet'); \
nltk.download('punkt_tab'); \
nltk.download('averaged_perceptron_tagger_eng')"
