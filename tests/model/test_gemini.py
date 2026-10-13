from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings


def test_key():
    api_key = input("Enter your Google API Key: ").strip()
    if not api_key:
        print("No key provided. Exiting.")
        return

    # print("\n[1/2] Testing Text Generation...")
    # try:
    #     llm = ChatGoogleGenerativeAI(
    #         model="gemini-1.5-flash", google_api_key=api_key, max_retries=0
    #     )
    #     response = llm.invoke("Say 'Hello, your API key is working!'")
    #     print("Success! Response:", response.content)
    # except Exception as e:
    #     print("Text Generation Failed:", e)

    print("\n[2/2] Testing Embeddings...")
    try:
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", google_api_key=api_key
        )
        vector = embeddings.embed_query("Test sentence")
        print(f"Success! Generated vector with {len(vector)} dimensions.")
    except Exception as e:
        print("Embeddings Failed:", e)


if __name__ == "__main__":
    test_key()